# Deployment: serving the cookbook at epel.cloud without touching the mirror

Status: **prepared, not executed**. Attaching Worker routes to the live zone is
a production change and needs Daniel's explicit approval. Everything up to and
including the Pages preview deploy is safe and reversible.

## Topology

The zone (`519b76b76f04405f25be9a7b851c6dd5`) keeps its current DNS: apex/www
proxied A records to Fedora dl02/dl03 (`38.145.32.23`, `.24`). The website
never becomes the origin. Instead:

| Layer | Object | Purpose |
|---|---|---|
| Cloudflare Pages | project `epel-cloud`, direct upload of `site/` | Hosts the static output at `epel-cloud.pages.dev` |
| Worker | `epel-cloud-site` (source: `deploy/worker.js`) | Serves an explicit allowlist of website paths from Pages; `fetch(request)` passthrough for everything else |
| Route 1 | `epel.cloud/pub/*` → **no script** | Mirror traffic never invokes the Worker: no website code and no Worker billing on package downloads |
| Route 2 | `epel.cloud/*` → `epel-cloud-site` | Covers `/`, query-bearing landing URLs, and the reserved paths |

Website paths served by the Worker: `/`, `/mirror`, `/recipes`, `/recipes/*`,
`/assets/*`, `/robots.txt`, `/sitemap.xml`, `/favicon.ico`, `/404.html`.
Everything else — including `/pub/*` (also bypassed at the route layer),
unknown paths, and existing redirects — goes to the origin unchanged.

`www.epel.cloud` gets **no route** in this phase: it keeps serving the mirror
exactly as today. All canonicals and the sitemap point at the apex, so search
engines index only apex URLs.

## What changes for existing mirror users: nothing

- `/pub/*` requests bypass the Worker at the route layer (more-specific route
  wins), hitting the same origin, cache rules, EPEL 7 page-rule redirect and
  transforms as today.
- The HTTP 400–599 never-edge-cache Cache Rule, the 31-day success TTL, the
  `User-Agent: libdnf (epel.cloud CDN)` request transform, `archive.` and
  `vault.` hosts are untouched.
- RPM bytes, GPG signatures, and Range responses are untouched (baseline
  captured in `evidence/baseline/` on 2026-10-11; re-verify after cutover with
  the checklist below).
- `robots.txt` changes deliberately: today it is Fedora's origin robots file
  (an AI-crawler blocklist); after cutover it is ours, which allows content
  crawling and adds `Disallow: /pub/` so crawlers stay out of the package
  tree. dnf is unaffected by robots.txt.

## Cutover procedure (needs approval)

1. Deploy current `site/` to Pages: `npx wrangler@latest pages deploy site
   --project-name=epel-cloud --branch=main` (also done by CI on master).
2. Spot-check `https://epel-cloud.pages.dev/` renders.
3. Upload the Worker:
   `npx wrangler@latest deploy deploy/worker.js --name epel-cloud-site
   --compatibility-date 2026-10-01` (no wrangler.toml routes; routes are added
   explicitly in the next step so ordering is controlled).
4. Add the **no-script route first**, then the catch-all:
   - `POST /zones/{zone}/workers/routes` with `{"pattern":"epel.cloud/pub/*","script":null}`
   - `POST /zones/{zone}/workers/routes` with `{"pattern":"epel.cloud/*","script":"epel-cloud-site"}`
5. Purge ONLY the replaced website URLs (never the mirror):
   `/`, `/robots.txt`, `/sitemap.xml`, `/favicon.ico` on `epel.cloud`
   (old cached root was a stale Anubis anti-bot page; a targeted purge evicts it).
6. Run the post-cutover checklist below.

## Post-cutover checklist (prove mirror equivalence)

Compare against `evidence/baseline/baseline-urls.txt` and
`baseline-range-sig.txt` (captured 2026-10-11):

- `curl -s https://epel.cloud/ | head` → cookbook HTML (not a Fedora listing,
  not Anubis).
- repomd.xml for EPEL 8/9/10 x86_64 + 9 aarch64 → HTTP 200, XML, fresh.
- `https://epel.cloud/pub/epel/7/x86_64/repodata/repomd.xml` → 301 to
  `archives.fedoraproject.org`.
- Range request on a known RPM → HTTP 206, correct `content-range`; sha256 of
  the full RPM matches the baseline
  (`758c9dcf…` for `fail2ban-server-1.1.0-6.el9.noarch.rpm`).
- Nonexistent mirror object `https://epel.cloud/pub/epel/9/nonexistent` →
  genuine error (404/30x from origin), NOT cookbook HTML, NOT edge-cached.
- `archive.epel.cloud` and `vault.epel.cloud` unchanged (no routes touch them).
- `https://epel.cloud/mirror?utm_source=test` → correct page (query-bearing
  URL through the wildcard route).
- End-to-end: `recipes-tests/run.sh mirror` (dnf against the live mirror from
  a clean container) still passes.
- `www.epel.cloud/pub/...` unchanged.

## Rollback

Delete the two Worker routes (`DELETE /zones/{zone}/workers/routes/{id}`).
The zone instantly reverts to today's behavior; the Worker and Pages project
can stay deployed, inert. No DNS, cache-rule or page-rule changes are made at
any point, so there is nothing else to restore. If the root was purged, the
origin re-populates it on next request (same as today's behavior).

## Costs

- Pages: free tier (static assets, well under limits).
- Worker: invoked only for website paths; `/pub/*` is excluded at the route
  layer. Expected volume (human visits) is far inside the free tier
  (100k req/day). Mirror traffic continues to be ordinary CDN traffic, not
  Worker invocations.
- Build: local/CI Python, seconds. No AI inference anywhere in build or serve.

## Maintenance

- Recipe freshness: re-run `recipes-tests/run.sh <slug>` and bump
  `last_tested`/`updated` frontmatter; the stamp on the page follows.
- New recipe: add `content/recipes/<slug>.md` + `recipes-tests/<slug>.sh`,
  run both, done — the index, sitemap and homepage pick it up at build time.
- Package versions shown in recipes are verified at test time, not scraped at
  build time; there is no scheduled crawling.
