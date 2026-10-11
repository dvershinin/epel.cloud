---
title: Encrypted server backups with restic
slug: restic-backups
description: Set up restic from EPEL on EL 9/10 for encrypted, deduplicated backups with a systemd timer, retention policy, integrity checks and a tested restore.
updated: 2026-10-11
last_tested: 2026-10-11
tested_on: AlmaLinux 9.8 and 10.2 systemd containers (aarch64)
releases: [EL 9, EL 10]
arches: [x86_64, aarch64]
time: 30 minutes
weight: 40
ingredients:
  - name: restic 0.18
    repo: EPEL
sources:
  - title: restic documentation
    url: https://restic.readthedocs.io/
  - title: restic repository design
    url: https://restic.readthedocs.io/en/stable/100_references.html
---

A backup you have never restored from is a hope, not a backup. restic, packaged
in EPEL, gives Enterprise Linux servers encrypted, deduplicated, incremental
backups to local disks, SFTP, or any S3-compatible bucket — with a restore
that is a single command. This recipe builds the full loop: repository,
scheduled backups, retention, integrity checking, and an actual verified
restore.

## Prerequisites

- AlmaLinux, Rocky Linux or RHEL 9/10 with root or sudo access.
- EPEL enabled: `sudo dnf install epel-release` ([mirror setup](/mirror)).
- A destination: a second disk, an SFTP host, or an S3-compatible bucket.
  The commands below use a local path `/backup/restic`; swap in
  `sftp:user@host:/srv/restic` or `s3:https://endpoint/bucket` — everything
  else stays identical.

## 1. Install restic

```
sudo dnf install restic
```

## 2. Create the repository

A restic *repository* is the encrypted destination store. Keep the password
in a root-only file so systemd units can use it non-interactively:

```
sudo install -d -m 700 /etc/restic
sudo sh -c 'head -c 32 /dev/urandom | base64 > /etc/restic/password'
sudo chmod 600 /etc/restic/password

sudo mkdir -p /backup/restic
sudo restic -r /backup/restic --password-file /etc/restic/password init
```

Expected: `created restic repository <id> at /backup/restic`.

**Copy `/etc/restic/password` somewhere off this machine now** (password
manager, sealed envelope — anywhere that survives the server dying). restic's
encryption has no backdoor: lose the password and the backups are noise.

## 3. First backup

Back up the directories that cannot be reinstalled from packages. A sensible
server baseline:

```
sudo restic -r /backup/restic --password-file /etc/restic/password \
  backup /etc /srv /var/lib --exclude /var/lib/dnf --exclude-caches
```

Expected (sizes vary):

```
snapshot 3f2a9c1b saved
```

Subsequent runs upload only changed blocks — deduplication is content-based,
so even renamed or copied files cost nothing.

## 4. Schedule it with a systemd timer

```
sudo tee /etc/systemd/system/restic-backup.service > /dev/null <<'EOF'
[Unit]
Description=restic backup
[Service]
Type=oneshot
Nice=10
IOSchedulingClass=idle
# restic needs a cache directory; systemd services have no $HOME, so without
# these two lines the unit fails with "unable to locate cache directory".
CacheDirectory=restic
Environment=RESTIC_CACHE_DIR=/var/cache/restic
ExecStart=/usr/bin/restic -r /backup/restic --password-file /etc/restic/password \
  backup /etc /srv /var/lib --exclude /var/lib/dnf --exclude-caches
ExecStartPost=/usr/bin/restic -r /backup/restic --password-file /etc/restic/password \
  forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
EOF

sudo tee /etc/systemd/system/restic-backup.timer > /dev/null <<'EOF'
[Unit]
Description=Daily restic backup
[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=30m
Persistent=true
[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now restic-backup.timer
```

The `forget --prune` line enforces retention: 7 daily, 4 weekly, 6 monthly
snapshots. Adjust to your recovery-point needs; `forget` without `--prune`
only unlinks snapshots and reclaims nothing.

## Verify: restore something and prove it matches

List snapshots, then restore into a scratch directory and compare checksums
against the live files:

```
sudo restic -r /backup/restic --password-file /etc/restic/password snapshots
sudo restic -r /backup/restic --password-file /etc/restic/password \
  restore latest --target /tmp/restore-test --include /etc/hostname
sha256sum /etc/hostname /tmp/restore-test/etc/hostname
```

Expected: both files produce the identical hash. That line is the difference
between "backups configured" and "backups work".

Run the repository integrity check (and make it a habit — monthly is a good
cadence; add it as another timer if the repository is large):

```
sudo restic -r /backup/restic --password-file /etc/restic/password check
```

Expected final line: `no errors were found`.

## Recovery notes

- **Full restore to a new machine:** install restic, copy
  `/etc/restic/password` back, then
  `restic -r <repo> restore latest --target /`. Do this onto a freshly
  installed OS, not a running production root.
- **Browse before restoring:** `restic mount /mnt/restic` (needs
  `fuse`) exposes every snapshot as a directory tree.
- **Repository on a dying disk:** `restic copy` can replicate the repository
  to a second destination, preserving snapshot history.

## Notes

- Local-disk repositories protect against deletion and bad deploys, not
  against the machine burning down. For real durability use SFTP or S3 as the
  destination, or `restic copy` to a second, offsite repository.
- restic encrypts client-side: the destination host or bucket provider never
  sees plaintext.
