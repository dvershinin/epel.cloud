# epel.cloud — Enterprise Linux cookbook

Static website for https://epel.cloud/: homepage, `/mirror` usage guide, and a
cookbook of tested Enterprise Linux recipes. The domain's primary role is a
free Cloudflare-cached EPEL mirror under `/pub/epel/` — the website must never
interfere with it. **Zero JavaScript, zero per-visitor AI, zero runtime
backends**: everything is generated HTML.

## Commands

- Build: `~/.virtualenvs/epelcloud/bin/epelcloud build` (emits `site/`)
- Local preview: `~/.virtualenvs/epelcloud/bin/epelcloud serve` → http://127.0.0.1:8322/
- Setup: `python3.12 -m venv ~/.virtualenvs/epelcloud && ~/.virtualenvs/epelcloud/bin/pip install -e . pytest`

## Testing

- **Fast suite (L1): `~/.virtualenvs/epelcloud/bin/pytest -q`** — builds into a
  tmp dir and asserts structure, internal links, canonicals/sitemap/robots,
  page-weight budgets, the no-JS guarantee, and the recipe content contract.
- **Recipe execution tests: `recipes-tests/run.sh <slug>`** — runs the recipe's
  commands end to end in a clean AlmaLinux 9 systemd container (Docker,
  `--privileged`). Full transcripts land in `evidence/recipes/`. These are NOT
  in CI (they take minutes and hit live repos); run them when a recipe
  changes, and update the recipe's `last_tested` frontmatter from the log.
- A recipe's "expected output" blocks must come from a captured transcript in
  `evidence/recipes/`, never from memory or docs.
- **W3C validation** (local Java is too old; use the dockerized checker):
  `docker run --rm -v "$PWD/site":/site ghcr.io/validator/validator:latest vnu --errors-only --skip-non-html /site`
  Zero errors required before pushing template changes. Known traps: no
  `aria-label` on role-less divs, no heading-level skips.

## Content model

- Recipes: `content/recipes/<slug>.md` with YAML frontmatter (title, slug,
  description, updated, last_tested, tested_on, releases, arches, time,
  ingredients, sources, weight for ordering). Body requires a `## Verify`
  section. Every recipe needs a matching `recipes-tests/<slug>.sh`.
- Mirror guide: `content/mirror.md`.
- Templates/CSS: `src/epelcloud/templates/`, `src/epelcloud/static/` —
  assets are content-hashed at build; reference via `{{ asset('css/main.css') }}`.
- URLs: extensionless, no trailing slash (`/recipes/fail2ban-ssh`); Cloudflare
  Pages maps `foo.html` → `/foo`. Canonicals always on the apex domain.

## CI / deployment

- CI is **myci** (`.myci/config.yml`): fast suite + build on every push;
  deploy to Cloudflare Pages (`epel-cloud` project, direct upload via
  wrangler) on master.
- Serving at epel.cloud = Worker + two routes; **attaching routes to the live
  zone is a production change requiring Daniel's explicit approval.** Read
  [docs/deploy.md](docs/deploy.md) before touching anything Cloudflare-side:
  it lists the mirror-preservation invariants (never purge the mirror, never
  touch `/pub/*` behavior, never repoint DNS, keep the 400–599 no-cache rule)
  and the rollback (delete the two routes).

## Hard rules

- Never claim a package is available/absent without a `pkg_available` check or
  a container transcript.
- Free install paths stay honest: if a package needs a subscription, the
  recipe says so; no fabricated scarcity or prices.
- The site describes itself as an independent mirror/cookbook, never an
  official Fedora/Red Hat service.
- No thousands of generated package pages; recipes are hand-written and
  individually tested.
