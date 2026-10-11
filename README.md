# epel.cloud

Static Enterprise Linux cookbook + mirror documentation for
[epel.cloud](https://epel.cloud/), a free Cloudflare-cached EPEL mirror.

- `src/epelcloud/` — small Python/Jinja2 static site generator (no JS output)
- `content/` — Markdown pages and recipes with YAML frontmatter
- `recipes-tests/` — every recipe executed end to end in a clean AlmaLinux
  systemd container; transcripts in `evidence/recipes/`
- `deploy/worker.js` + `docs/deploy.md` — Cloudflare topology that serves the
  site at the apex while `/pub/*` mirror traffic bypasses website code entirely

Build: `pip install -e . && epelcloud build` → `site/`.
Test: `pytest`.
