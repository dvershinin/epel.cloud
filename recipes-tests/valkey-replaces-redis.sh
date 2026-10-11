#!/usr/bin/env bash
# Mirrors content/recipes/valkey-replaces-redis.md, including the Redis->Valkey
# RDB migration: seed a real Redis 7.2 (AppStream) instance, move its dump into
# Valkey, and prove the data arrives and survives a Valkey restart.
set -euxo pipefail

# EL9 ships redis 7.2 in AppStream, so we test the documented migration path.
# EL10 has no redis package at all (valkey replaced it): there the recipe's
# "new install" path applies and the migration steps are skipped.
HAVE_REDIS=0
if dnf -y install redis; then
  HAVE_REDIS=1
  echo "=== seed a Redis instance to migrate from ==="
  systemctl enable --now redis
  redis-cli set migrated:key "came-from-redis"
  redis-cli save
else
  echo "=== no redis package on this release; testing the new-install path ==="
fi

echo "=== 1. install valkey ==="
dnf -y install valkey

echo "=== 2. configure (append; last directive wins) ==="
tee -a /etc/valkey/valkey.conf > /dev/null <<'EOF'

# --- local tuning ---
maxmemory 256mb
maxmemory-policy allkeys-lru
EOF

if [ "$HAVE_REDIS" = 1 ]; then
  echo "=== 3. migrate the dump ==="
  systemctl stop redis
  cp /var/lib/redis/dump.rdb /var/lib/valkey/dump.rdb
  chown valkey:valkey /var/lib/valkey/dump.rdb
fi

echo "=== 4. start valkey ==="
systemctl enable --now valkey

echo "=== verify ==="
valkey-cli ping
valkey-cli set cookbook:test "epel.cloud"
valkey-cli get cookbook:test
if [ "$HAVE_REDIS" = 1 ]; then
  echo "=== migrated key present ==="
  valkey-cli get migrated:key
  valkey-cli get migrated:key | grep -q 'came-from-redis'
fi

echo "=== persistence across restart ==="
systemctl restart valkey
sleep 2
valkey-cli get cookbook:test
valkey-cli get cookbook:test | grep -q 'epel.cloud'
valkey-cli dbsize

echo "=== config tuning honored ==="
valkey-cli config get maxmemory-policy
valkey-cli config get maxmemory-policy | grep -q allkeys-lru

echo "RECIPE OK"
