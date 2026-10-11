#!/usr/bin/env bash
# Mirrors content/recipes/restic-backups.md step by step.
set -euxo pipefail

dnf -y install epel-release
dnf -y install restic

echo "=== 2. create the repository ==="
install -d -m 700 /etc/restic
sh -c 'head -c 32 /dev/urandom | base64 > /etc/restic/password'
chmod 600 /etc/restic/password
mkdir -p /backup/restic
restic -r /backup/restic --password-file /etc/restic/password init

echo "=== 3. first backup ==="
mkdir -p /srv
restic -r /backup/restic --password-file /etc/restic/password \
  backup /etc /srv /var/lib --exclude /var/lib/dnf --exclude-caches

echo "=== 4. timer ==="
tee /etc/systemd/system/restic-backup.service > /dev/null <<'EOF'
[Unit]
Description=restic backup
[Service]
Type=oneshot
Nice=10
IOSchedulingClass=idle
CacheDirectory=restic
Environment=RESTIC_CACHE_DIR=/var/cache/restic
ExecStart=/usr/bin/restic -r /backup/restic --password-file /etc/restic/password \
  backup /etc /srv /var/lib --exclude /var/lib/dnf --exclude-caches
ExecStartPost=/usr/bin/restic -r /backup/restic --password-file /etc/restic/password \
  forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
EOF

tee /etc/systemd/system/restic-backup.timer > /dev/null <<'EOF'
[Unit]
Description=Daily restic backup
[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=30m
Persistent=true
[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now restic-backup.timer
systemctl list-timers restic-backup.timer --no-pager

echo "=== timer service actually runs ==="
systemctl start restic-backup.service
systemctl status restic-backup.service --no-pager -l | tail -5 || true

echo "=== verify: restore and compare ==="
restic -r /backup/restic --password-file /etc/restic/password snapshots
restic -r /backup/restic --password-file /etc/restic/password \
  restore latest --target /tmp/restore-test --include /etc/hostname
sha256sum /etc/hostname /tmp/restore-test/etc/hostname
A=$(sha256sum /etc/hostname | awk '{print $1}')
B=$(sha256sum /tmp/restore-test/etc/hostname | awk '{print $1}')
[ "$A" = "$B" ]

echo "=== repository check ==="
restic -r /backup/restic --password-file /etc/restic/password check
restic -r /backup/restic --password-file /etc/restic/password check 2>&1 | grep -q 'no errors were found'

echo "RECIPE OK"
