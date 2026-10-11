"""Fast suite: build the site into a tmp dir and assert structural invariants."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from epelcloud.build import BASE_URL, build

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Page-weight budgets (bytes). The whole point of a static cookbook is speed.
HTML_BUDGET = 60 * 1024
CSS_BUDGET = 24 * 1024


@pytest.fixture(scope="session")
def site(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("site")
    build(PROJECT_ROOT / "content", out)
    return out


def html_files(site: Path) -> list[Path]:
    return sorted(site.rglob("*.html"))


class PageScanner(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.canonical: str | None = None
        self.description: str | None = None
        self.title_parts: list[str] = []
        self._in_title = False
        self._script_type: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "link":
            if attrs.get("rel") == "canonical":
                self.canonical = attrs.get("href")
            if attrs.get("href"):
                self.links.append(attrs["href"])
        if tag == "script":
            self._script_type = attrs.get("type", "")
            self.scripts.append(self._script_type)
        if tag == "meta" and attrs.get("name") == "description":
            self.description = attrs.get("content")
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return "".join(self.title_parts).strip()


def scan(path: Path) -> PageScanner:
    scanner = PageScanner()
    scanner.feed(path.read_text(encoding="utf-8"))
    return scanner


def test_expected_pages_exist(site: Path):
    for rel in ("index.html", "mirror.html", "recipes.html", "404.html",
                "sitemap.xml", "robots.txt", "_headers"):
        assert (site / rel).exists(), f"missing {rel}"
    recipes = list((site / "recipes").glob("*.html"))
    assert len(recipes) >= 5, "cookbook must ship at least five recipes"


def test_no_javascript_anywhere(site: Path):
    """Essential content must work without JS; we go further: no JS at all.

    JSON-LD <script type=application/ld+json> blocks are data, not script.
    """
    for page in html_files(site):
        scanner = scan(page)
        executable = [t for t in scanner.scripts if t != "application/ld+json"]
        assert not executable, f"{page} contains executable script tags: {executable}"


def test_internal_links_resolve(site: Path):
    for page in html_files(site):
        for href in scan(page).links:
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            path = href.split("#", 1)[0]
            if not path or path.startswith("#"):
                continue
            assert path.startswith("/"), f"{page}: non-root-relative link {href}"
            if path.startswith("/pub/"):
                continue  # mirror namespace, served by the CDN, not this site
            target = site / path.lstrip("/")
            candidates = [
                target,
                target.with_suffix(".html") if not target.suffix else target,
                target / "index.html",
            ]
            assert any(c.exists() for c in candidates), f"{page}: broken link {href}"


def test_titles_descriptions_canonicals(site: Path):
    titles = {}
    for page in html_files(site):
        scanner = scan(page)
        assert scanner.title, f"{page} missing <title>"
        assert scanner.title not in titles, f"duplicate title: {scanner.title}"
        titles[scanner.title] = page
        assert scanner.description, f"{page} missing meta description"
        assert 50 <= len(scanner.description) <= 170, (
            f"{page} description length {len(scanner.description)}"
        )
        if page.name != "404.html":
            assert scanner.canonical, f"{page} missing canonical"
            assert scanner.canonical.startswith(BASE_URL), scanner.canonical
            assert not scanner.canonical.endswith("/") or scanner.canonical == f"{BASE_URL}/", (
                f"{page}: canonical must not have a trailing slash: {scanner.canonical}"
            )


def test_sitemap_matches_pages(site: Path):
    sitemap = (site / "sitemap.xml").read_text(encoding="utf-8")
    locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    assert locs, "empty sitemap"
    for loc in locs:
        assert loc.startswith(BASE_URL)
        path = loc[len(BASE_URL):] or "/"
        rel = "index.html" if path == "/" else path.lstrip("/") + ".html"
        assert (site / rel).exists(), f"sitemap entry without page: {loc}"
    # Every canonical page is in the sitemap.
    for page in html_files(site):
        if page.name == "404.html":
            continue
        canonical = scan(page).canonical
        assert canonical in locs, f"{page} canonical {canonical} missing from sitemap"


def test_robots(site: Path):
    robots = (site / "robots.txt").read_text(encoding="utf-8")
    assert "Disallow: /pub/" in robots, "crawlers must stay out of the mirror tree"
    assert f"Sitemap: {BASE_URL}/sitemap.xml" in robots


def test_page_weight_budgets(site: Path):
    for page in html_files(site):
        size = page.stat().st_size
        assert size <= HTML_BUDGET, f"{page} is {size} bytes (budget {HTML_BUDGET})"
    css = list((site / "assets").rglob("*.css"))
    assert css, "missing stylesheet"
    for sheet in css:
        assert sheet.stat().st_size <= CSS_BUDGET, f"{sheet} over CSS budget"


def test_assets_are_hashed_and_referenced(site: Path):
    for asset in (site / "assets").rglob("*"):
        if asset.is_file():
            assert re.search(r"\.[0-9a-f]{8}\.", asset.name), f"unhashed asset {asset}"
    home = (site / "index.html").read_text(encoding="utf-8")
    assert re.search(r"/assets/css/main\.[0-9a-f]{8}\.css", home)


def test_recipe_content_contract(site: Path):
    """Each recipe page carries the trust markers the cookbook promises."""
    for page in (site / "recipes").glob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "Tested" in text, f"{page} missing tested stamp"
        assert "Ingredients" in text, f"{page} missing ingredients"
        assert "Sources" in text, f"{page} missing sources"
        assert re.search(r"<h2[^>]*>Verify", text), f"{page} missing a Verify section"
        assert "application/ld+json" in text, f"{page} missing JSON-LD"


def test_mirror_page_documents_the_real_namespace(site: Path):
    mirror = (site / "mirror.html").read_text(encoding="utf-8")
    assert "https://epel.cloud/pub/epel/" in mirror
    assert "gpgcheck" in mirror


def test_headers_file_for_immutable_assets(site: Path):
    headers = (site / "_headers").read_text(encoding="utf-8")
    assert "/assets/*" in headers and "immutable" in headers
