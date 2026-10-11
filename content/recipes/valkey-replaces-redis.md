---
title: Replace Redis with Valkey on EL 9/10
slug: valkey-replaces-redis
description: Install Valkey from AppStream on AlmaLinux, Rocky Linux or RHEL 9/10, migrate an existing Redis dump, and verify persistence across restarts.
updated: 2026-10-11
last_tested: 2026-10-11
tested_on: AlmaLinux 9.8 and 10.2 systemd containers (aarch64)
releases: [EL 9, EL 10]
arches: [x86_64, aarch64]
time: 20 minutes
weight: 20
ingredients:
  - name: valkey 8.0
    repo: AppStream
sources:
  - title: Valkey documentation
    url: https://valkey.io/docs/
  - title: "RHEL 10: considerations in adopting"
    url: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/considerations_in_adopting_rhel_10/index
---

After Redis moved away from its open-source license in 2024, Enterprise Linux
adopted [Valkey](https://valkey.io/), the Linux Foundation fork, as the
in-distribution replacement. RHEL 10 ships Valkey instead of Redis, and
RHEL 9 carries it in AppStream alongside the final open-source Redis. Valkey 8
speaks the same protocol (RESP), reads the same `dump.rdb` files, and existing
Redis client libraries connect to it unmodified.

This recipe installs Valkey, carries data over from a running Redis instance,
and verifies persistence survives a restart.

## Prerequisites

- AlmaLinux, Rocky Linux or RHEL 9/10 with root or sudo access.
- If migrating: an existing Redis 6/7 instance whose data you want to keep.
  New installs can skip step 3.

## 1. Install Valkey

Valkey lives in AppStream, the distribution's own repository, so no extra
repos are needed:

```
sudo dnf install valkey
```

## 2. Configure

The configuration file is `/etc/valkey/valkey.conf` and uses the same
directives as `redis.conf`. The packaged defaults already bind to
`127.0.0.1` only. For a typical cache/session store, set a memory ceiling and
an eviction policy by appending to the config — in this format the last
occurrence of a directive wins, and dnf treats the file as `noreplace`, so
your tuning survives package updates:

```
sudo tee -a /etc/valkey/valkey.conf > /dev/null <<'EOF'

# --- local tuning ---
maxmemory 256mb
maxmemory-policy allkeys-lru
EOF
```

(The EL package has no `conf.d` include directory; the appended block plays
that role.)

If anything other than localhost must connect, set `requirepass` (or ACLs)
**before** changing `bind` — never expose an unauthenticated instance to a
network.

## 3. Migrate data from Redis (optional)

Valkey 8 reads Redis RDB dumps directly. Stop the old service so the dump is
consistent, copy it into Valkey's data directory, and fix ownership:

```
sudo systemctl stop redis
sudo cp /var/lib/redis/dump.rdb /var/lib/valkey/dump.rdb
sudo chown valkey:valkey /var/lib/valkey/dump.rdb
```

If your Redis used AOF persistence (`appendonly yes`), either trigger a final
RDB snapshot first (`redis-cli save`), or copy the `appendonlydir/` across and
enable `appendonly yes` in a Valkey drop-in too.

## 4. Start and enable

```
sudo systemctl enable --now valkey
```

## Verify

The client tool is `valkey-cli`; it speaks to anything RESP-compatible:

```
valkey-cli ping
valkey-cli set cookbook:test "epel.cloud"
valkey-cli get cookbook:test
```

Expected:

```
PONG
OK
"epel.cloud"
```

Confirm the data survives a service restart (this proves persistence is
actually configured, not assumed):

```
sudo systemctl restart valkey
valkey-cli get cookbook:test
```

Expected: `"epel.cloud"` again. If you migrated from Redis, spot-check a few
known keys the same way, and compare key counts with `valkey-cli dbsize`
against the old instance's `redis-cli dbsize`. Confirm the tuning took:

```
valkey-cli config get maxmemory-policy
```

Expected:

```
1) "maxmemory-policy"
2) "allkeys-lru"
```

Your applications keep using their existing Redis client libraries and
connection URLs; only the port's listener changed. If an app hardcodes the
`redis-cli` binary, note that Valkey ships `valkey-cli` instead.

## Recovery

The old Redis instance and its data are untouched by this recipe: stopping
Valkey and starting Redis again (`sudo systemctl disable --now valkey &&
sudo systemctl start redis`) is a full rollback, as long as you have not
written new data you need into Valkey in the meantime. Writes made only to
Valkey after the cutover do not flow back to Redis.

## Notes

- RHEL 9 keeps Redis 7.2 (the last open-source release) in AppStream through
  the EL 9 lifecycle, so this migration is about staying on a maintained
  upstream, not an emergency.
- On EL 10 there is no `redis` package; `valkey` is the path.
- Valkey honors `maxmemory-policy` exactly as Redis does; the
  [Valkey docs](https://valkey.io/docs/) cover the policy options.
