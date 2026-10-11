---
title: Serve Brotli-compressed pages with NGINX
slug: nginx-brotli
description: Enable Brotli compression in NGINX on EL 9/10 with prebuilt RPMs - the in-distro EPEL module or GetPageSpeed's current-NGINX build - with measured size savings.
updated: 2026-10-11
last_tested: 2026-10-11
tested_on: AlmaLinux 9.8 and 10.2 systemd containers (aarch64), both options
releases: [EL 9, EL 10]
arches: [x86_64, aarch64]
time: 20 minutes
weight: 50
ingredients:
  - name: nginx-mod-brotli
    repo: EPEL (for the AppStream nginx)
  - name: nginx 1.30 + nginx-module-brotli
    repo: GetPageSpeed (current nginx, alternative)
sources:
  - title: ngx_brotli module
    url: https://github.com/google/ngx_brotli
  - title: GetPageSpeed NGINX Extras
    url: https://nginx-extras.getpagespeed.com/
---

Brotli compresses text assets 15–25% smaller than gzip at comparable CPU
cost, and every modern browser sends `Accept-Encoding: br`. NGINX has no
built-in Brotli support — it needs the `ngx_brotli` dynamic module, and a
dynamic module must be compiled against the exact NGINX version it loads
into, which is why "download a .so from somewhere" breaks on the next update.

On Enterprise Linux there are two packaged routes, both tested here:

| Route | NGINX | Module package | Good when |
|---|---|---|---|
| A: in-distro | AppStream nginx (1.20 on EL9, 1.26 on EL10) | `nginx-mod-brotli` (EPEL) | You want only distro + EPEL packages |
| B: current NGINX | nginx 1.30.x | `nginx-module-brotli` ([GetPageSpeed](https://www.getpagespeed.com/)) | You want current upstream NGINX and a wider module catalog that stays ABI-matched |

## Prerequisites

- AlmaLinux, Rocky Linux or RHEL 9/10 with root or sudo access, and no other
  web server on port 80.

## Option A: AppStream NGINX + EPEL module

```
sudo dnf install epel-release
sudo dnf install nginx nginx-mod-brotli
```

The EPEL module package drops `/usr/share/nginx/modules/mod-brotli.conf`,
which the stock `nginx.conf` includes automatically — **no `load_module`
lines needed** on this route. Note that EL9's AppStream nginx is 1.20
(released 2021); it is maintained by the distribution, just old.

Skip to [configuration](#configure-compression) below.

## Option B: current NGINX from GetPageSpeed

The [GetPageSpeed repository](https://www.getpagespeed.com/) carries current
stable NGINX plus ~100 modules prebuilt against it, so `dnf update` keeps
module and server ABI-matched automatically. Add the repo:

```
sudo dnf install https://extras.getpagespeed.com/release-latest.rpm
```

The packages used here install without a subscription (verified from a clean,
unsubscribed network on the tested date);
[subscriptions](https://www.getpagespeed.com/repo-subscribe) fund the
packaging work and unlock the full module set, newer channels and support.

```
sudo dnf install nginx nginx-module-brotli
```

This route's NGINX is 1.30.x; the module installs its `.so` files into
`/usr/lib64/nginx/modules/` and here you **do** load them explicitly at the
top of `/etc/nginx/nginx.conf` (before any blocks):

```
load_module modules/ngx_http_brotli_filter_module.so;
load_module modules/ngx_http_brotli_static_module.so;
```

## Configure compression

Identical for both routes:

```
sudo tee /etc/nginx/conf.d/brotli.conf > /dev/null <<'EOF'
brotli on;
brotli_comp_level 6;
brotli_min_length 256;
brotli_types text/plain text/css text/xml application/javascript
             application/json application/xml image/svg+xml;

# Serve pre-compressed .br files when present (zero CPU per request).
brotli_static on;
EOF
```

`text/html` is always compressed when `brotli on` is set; listing it in
`brotli_types` is unnecessary (NGINX warns about the duplicate).

## Validate and start

```
sudo nginx -t
sudo systemctl enable --now nginx
```

Expected from `nginx -t`:

```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

## Verify

Ask for the default page with and without Brotli support:

```
curl -sI -H 'Accept-Encoding: br' http://localhost/ | grep -i content-encoding
curl -so /dev/null -w '%{size_download} bytes (br)\n'    -H 'Accept-Encoding: br' http://localhost/
curl -so /dev/null -w '%{size_download} bytes (plain)\n' http://localhost/
```

Expected: `Content-Encoding: br`, with a visibly smaller transfer. Measured on
the default welcome page during testing:

| Route | Brotli | Uncompressed |
|---|---|---|
| A (EPEL, nginx 1.20) | 1796 bytes | 5760 bytes |
| B (GetPageSpeed, nginx 1.30) | 423 bytes | 896 bytes |

(The two welcome pages differ in size; compare within a row, not across.)
Clients that do not advertise `br` transparently fall back to gzip or
identity — negotiation is per-request, so enabling Brotli is safe for every
client.

## Recovery

Remove `/etc/nginx/conf.d/brotli.conf` (and on route B the two `load_module`
lines), then `sudo nginx -t && sudo systemctl reload nginx`. Package rollback
is ordinary dnf: `sudo dnf remove nginx-mod-brotli` (A) or
`sudo dnf remove nginx-module-brotli` (B).

## Notes

- For static assets, pre-compress at deploy time
  (`brotli -k -q 11 app.css` — the `brotli` CLI is in BaseOS) and let
  `brotli_static on` serve the `.br` files: maximum compression with zero
  request-time CPU.
- Compression level 6 is the sweet spot for dynamic responses; 11 is for
  pre-compression only.
- Do not enable Brotli (or gzip) for responses that mix secrets with
  attacker-controlled input — the BREACH class of attacks applies to any
  HTTPS compression. For ordinary pages and assets it is a non-issue.
- Needing more than Brotli (headers-more, GeoIP2, VTS metrics, PageSpeed…) is
  the usual reason to pick route B — the
  [module index](https://nginx-extras.getpagespeed.com/) lists what's
  packaged.
