#!/usr/bin/env bash
# Mirrors content/recipes/nginx-brotli.md step by step.
set -euxo pipefail

echo "=== 1. add the repository ==="
dnf -y install https://extras.getpagespeed.com/release-latest.rpm

echo "=== 2. install nginx + brotli module ==="
dnf -y install nginx nginx-module-brotli
nginx -v
rpm -q nginx nginx-module-brotli
echo "=== module files ==="
rpm -ql nginx-module-brotli

echo "=== 3. load and configure ==="
# Insert load_module lines at the top of nginx.conf.
sed -i '1i load_module modules/ngx_http_brotli_filter_module.so;\nload_module modules/ngx_http_brotli_static_module.so;' /etc/nginx/nginx.conf

tee /etc/nginx/conf.d/brotli.conf > /dev/null <<'EOF'
brotli on;
brotli_comp_level 6;
brotli_min_length 256;
brotli_types text/plain text/css text/xml application/javascript
             application/json application/xml image/svg+xml;

brotli_static on;
EOF

echo "=== 4. validate and start ==="
nginx -t
systemctl enable --now nginx
sleep 2

echo "=== verify ==="
curl -sI -H 'Accept-Encoding: br' http://localhost/ | grep -i content-encoding
curl -sI -H 'Accept-Encoding: br' http://localhost/ | grep -qi 'content-encoding: br'
curl -sI -H 'Accept-Encoding: gzip' http://localhost/ | grep -i content-encoding || echo "(no gzip header: gzip may be off by default)"
curl -so /dev/null -w '%{size_download} bytes (br)\n'    -H 'Accept-Encoding: br'   http://localhost/
curl -so /dev/null -w '%{size_download} bytes (plain)\n' http://localhost/

BR=$(curl -so /dev/null -w '%{size_download}' -H 'Accept-Encoding: br' http://localhost/)
PLAIN=$(curl -so /dev/null -w '%{size_download}' http://localhost/)
[ "$BR" -lt "$PLAIN" ]

echo "RECIPE OK"
