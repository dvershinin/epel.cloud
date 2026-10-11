#!/usr/bin/env bash
# Mirrors content/recipes/nginx-brotli.md, Option A: the in-distro route
# (AppStream nginx + EPEL nginx-mod-brotli).
set -euxo pipefail

echo "=== install nginx + EPEL brotli module ==="
dnf -y install epel-release
dnf -y install nginx nginx-mod-brotli
nginx -v
rpm -q nginx nginx-mod-brotli
echo "=== module files ==="
rpm -ql nginx-mod-brotli

echo "=== configure ==="
tee /etc/nginx/conf.d/brotli.conf > /dev/null <<'EOF'
brotli on;
brotli_comp_level 6;
brotli_min_length 256;
brotli_types text/plain text/css text/xml application/javascript
             application/json application/xml image/svg+xml;

brotli_static on;
EOF

echo "=== validate and start ==="
nginx -t
systemctl enable --now nginx
sleep 2

echo "=== verify ==="
curl -sI -H 'Accept-Encoding: br' http://localhost/ | grep -i content-encoding
curl -sI -H 'Accept-Encoding: br' http://localhost/ | grep -qi 'content-encoding: br'
curl -so /dev/null -w '%{size_download} bytes (br)\n'    -H 'Accept-Encoding: br'   http://localhost/
curl -so /dev/null -w '%{size_download} bytes (plain)\n' http://localhost/

BR=$(curl -so /dev/null -w '%{size_download}' -H 'Accept-Encoding: br' http://localhost/)
PLAIN=$(curl -so /dev/null -w '%{size_download}' http://localhost/)
[ "$BR" -lt "$PLAIN" ]

echo "RECIPE OK"
