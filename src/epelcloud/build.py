"""Build the epel.cloud static site.

Reads Markdown recipes with YAML frontmatter from ``content/``, renders
Jinja2 templates, content-hashes static assets, and emits a fully static
tree into ``site/``. No JavaScript is emitted anywhere; serving the site
requires nothing beyond a static file host.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

PACKAGE_DIR = Path(__file__).resolve().parent
BASE_URL = "https://epel.cloud"

MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists", "toc"]

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)

REQUIRED_RECIPE_KEYS = {
    "title",
    "slug",
    "description",
    "updated",
    "last_tested",
    "tested_on",
    "releases",
    "arches",
    "time",
    "ingredients",
    "sources",
}


@dataclass
class Recipe:
    meta: dict
    body_html: str

    @property
    def slug(self) -> str:
        return self.meta["slug"]

    @property
    def url(self) -> str:
        return f"/recipes/{self.slug}"


@dataclass
class Site:
    content_dir: Path
    out_dir: Path
    recipes: list[Recipe] = field(default_factory=list)
    assets: dict[str, str] = field(default_factory=dict)


def split_frontmatter(text: str, origin: Path) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{origin}: missing YAML frontmatter")
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise ValueError(f"{origin}: frontmatter is not a mapping")
    return meta, match.group(2)


def render_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=MD_EXTENSIONS)


def load_recipes(content_dir: Path) -> list[Recipe]:
    recipes = []
    for path in sorted((content_dir / "recipes").glob("*.md")):
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"), path)
        missing = REQUIRED_RECIPE_KEYS - meta.keys()
        if missing:
            raise ValueError(f"{path}: missing frontmatter keys: {sorted(missing)}")
        for key in ("updated", "last_tested"):
            if not isinstance(meta[key], date):
                raise ValueError(f"{path}: {key} must be a YYYY-MM-DD date")
        recipes.append(Recipe(meta=meta, body_html=render_markdown(body)))
    recipes.sort(key=lambda recipe: recipe.meta.get("weight", 100))
    return recipes


def load_page(content_dir: Path, name: str) -> tuple[dict, str]:
    path = content_dir / f"{name}.md"
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"), path)
    return meta, render_markdown(body)


def hash_assets(out_dir: Path) -> dict[str, str]:
    """Copy static assets into the output with a content hash in the name."""
    manifest: dict[str, str] = {}
    static_dir = PACKAGE_DIR / "static"
    for path in sorted(static_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(static_dir)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
        hashed_name = f"{path.stem}.{digest}{path.suffix}"
        target_rel = rel.parent / hashed_name
        target = out_dir / "assets" / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        manifest[str(rel)] = f"/assets/{target_rel}"
    return manifest


def jinja_env(assets: dict[str, str]) -> Environment:
    env = Environment(
        loader=FileSystemLoader(PACKAGE_DIR / "templates"),
        undefined=StrictUndefined,
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def asset(logical: str) -> str:
        return assets[logical]

    env.globals["asset"] = asset
    env.globals["base_url"] = BASE_URL
    env.globals["build_date"] = date.today().isoformat()
    env.filters["tojson_ld"] = lambda value: json.dumps(value, ensure_ascii=False)
    return env


def write_page(out_dir: Path, rel: str, html: str) -> None:
    target = out_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")


def recipe_json_ld(recipe: Recipe) -> dict:
    meta = recipe.meta
    return {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": meta["title"],
        "description": meta["description"],
        "url": f"{BASE_URL}{recipe.url}",
        "dateModified": meta["updated"].isoformat(),
        "inLanguage": "en",
        "isPartOf": {
            "@type": "WebSite",
            "name": "epel.cloud",
            "url": BASE_URL,
        },
    }


def build(content_dir: Path, out_dir: Path) -> Site:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    assets = hash_assets(out_dir)
    env = jinja_env(assets)
    site = Site(content_dir=content_dir, out_dir=out_dir, assets=assets)
    site.recipes = load_recipes(content_dir)

    mirror_meta, mirror_html = load_page(content_dir, "mirror")

    pages = []  # (path on disk, canonical path, lastmod)

    html = env.get_template("home.html").render(
        recipes=site.recipes,
        canonical=f"{BASE_URL}/",
    )
    write_page(out_dir, "index.html", html)
    pages.append(("index.html", "/", max(r.meta["updated"] for r in site.recipes)))

    html = env.get_template("mirror.html").render(
        meta=mirror_meta,
        body=mirror_html,
        canonical=f"{BASE_URL}/mirror",
    )
    write_page(out_dir, "mirror.html", html)
    pages.append(("mirror.html", "/mirror", mirror_meta["updated"]))

    html = env.get_template("recipes.html").render(
        recipes=site.recipes,
        canonical=f"{BASE_URL}/recipes",
    )
    write_page(out_dir, "recipes.html", html)
    pages.append(
        ("recipes.html", "/recipes", max(r.meta["updated"] for r in site.recipes))
    )

    recipe_template = env.get_template("recipe.html")
    for recipe in site.recipes:
        html = recipe_template.render(
            recipe=recipe,
            canonical=f"{BASE_URL}{recipe.url}",
            json_ld=recipe_json_ld(recipe),
        )
        write_page(out_dir, f"recipes/{recipe.slug}.html", html)
        pages.append(
            (f"recipes/{recipe.slug}.html", recipe.url, recipe.meta["updated"])
        )

    html = env.get_template("404.html").render(canonical=None)
    write_page(out_dir, "404.html", html)

    sitemap_entries = "\n".join(
        f"  <url><loc>{BASE_URL}{path}</loc><lastmod>{lastmod.isoformat()}</lastmod></url>"
        for _, path, lastmod in pages
    )
    write_page(
        out_dir,
        "sitemap.xml",
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{sitemap_entries}\n</urlset>\n",
    )

    write_page(
        out_dir,
        "robots.txt",
        "User-agent: *\n"
        "Disallow: /pub/\n"
        "\n"
        f"Sitemap: {BASE_URL}/sitemap.xml\n",
    )

    # Cloudflare Pages header rules: hashed assets are immutable.
    write_page(
        out_dir,
        "_headers",
        "/assets/*\n"
        "  Cache-Control: public, max-age=31536000, immutable\n"
        "/*\n"
        "  X-Content-Type-Options: nosniff\n",
    )

    return site


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build", help="Build the static site")
    build_parser.add_argument("--content", type=Path, default=Path("content"))
    build_parser.add_argument("--out", type=Path, default=Path("site"))

    serve_parser = sub.add_parser("serve", help="Serve the built site locally")
    serve_parser.add_argument("--out", type=Path, default=Path("site"))
    serve_parser.add_argument("--port", type=int, default=8322)

    args = parser.parse_args(argv)

    if args.command == "build":
        site = build(args.content.resolve(), args.out.resolve())
        print(f"Built {len(site.recipes)} recipes into {args.out}")
        return 0

    if args.command == "serve":
        import functools
        import http.server

        # Resolve extensionless URLs the way Cloudflare Pages does.
        class Handler(http.server.SimpleHTTPRequestHandler):
            def translate_path(self, path: str) -> str:
                resolved = super().translate_path(path)
                candidate = Path(resolved)
                if not candidate.exists() and not candidate.suffix:
                    html = candidate.with_suffix(".html")
                    if html.exists():
                        return str(html)
                return resolved

        handler = functools.partial(Handler, directory=str(args.out))
        with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
            print(f"Serving {args.out} at http://127.0.0.1:{args.port}/")
            httpd.serve_forever()

    return 0


if __name__ == "__main__":
    sys.exit(main())
