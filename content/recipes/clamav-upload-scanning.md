---
title: Scan uploads for malware with ClamAV
slug: clamav-upload-scanning
description: Run the clamd scanning daemon from EPEL on EL 9/10, keep signatures fresh with freshclam, scan web upload directories on a timer, and verify detection with EICAR.
updated: 2026-10-11
last_tested: 2026-10-11
tested_on: AlmaLinux 9.8 and 10.2 systemd containers (aarch64)
releases: [EL 9, EL 10]
arches: [x86_64, aarch64]
time: 30 minutes
weight: 30
ingredients:
  - name: clamav 1.4
    repo: EPEL
  - name: clamd 1.4
    repo: EPEL
  - name: clamav-freshclam 1.4
    repo: EPEL
sources:
  - title: ClamAV documentation
    url: https://docs.clamav.net/
  - title: EICAR test file
    url: https://www.eicar.org/download-anti-malware-testfile/
---

If your server accepts files from the outside world — a web app with uploads,
an SFTP drop, a mail spool — scanning those files is cheap insurance and often
a compliance checkbox. EPEL ships ClamAV, the standard open-source scanner.
The useful setup is the `clamd` daemon (signatures stay loaded in memory, so
each scan takes milliseconds) plus `freshclam` (keeps signatures current) plus
a systemd timer sweeping your upload directory.

## Prerequisites

- AlmaLinux, Rocky Linux or RHEL 9/10 with root or sudo access.
- EPEL enabled: `sudo dnf install epel-release` ([mirror setup](/mirror)).
- About 1.5 GB of free RAM for the daemon: clamd loads the entire signature
  database into memory. Don't deploy this on a 1 GB VPS.

## 1. Install the scanner, daemon and updater

```
sudo dnf install clamav clamd clamav-update
```

## 2. Fetch signatures

The daemon refuses to start without a signature database, so run the updater
once by hand, then keep it running as a service:

```
sudo freshclam
sudo systemctl enable --now clamav-freshclam
```

The first download fetches the full databases (roughly 300 MB) from
`database.clamav.net`; later runs are incremental diffs.

## 3. Configure and start clamd

The EL package is instance-based: `/etc/clamd.d/scan.conf` defines the `scan`
instance, run as `clamd@scan`. Enable its local socket:

```
sudo sed -i 's|^#LocalSocket /run/clamd.scan/clamd.sock|LocalSocket /run/clamd.scan/clamd.sock|' /etc/clamd.d/scan.conf
sudo systemctl enable --now clamd@scan
```

The first start takes a while (loading signatures); watch it with
`journalctl -u clamd@scan -f` until you see `Listening daemon: PID`.

## Verify

Use the standard EICAR test string — every scanner must flag it, and it is
harmless:

```
printf 'X5O!P%%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > /tmp/eicar.txt
clamdscan --fdpass /tmp/eicar.txt
```

Expected output:

```
/tmp/eicar.txt: Eicar-Test-Signature FOUND

----------- SCAN SUMMARY -----------
Infected files: 1
Time: 0.001 sec (0 m 0 s)
```

`--fdpass` makes your shell open the file and pass the descriptor to the
daemon, which sidesteps file-permission mismatches between your user and the
`clamscan` service user.

## 4. Sweep an upload directory on a timer

Scheduled sweeps catch anything that arrived between real-time checks.
Replace `/srv/uploads` with your actual upload path:

```
sudo tee /etc/systemd/system/clamdscan-uploads.service > /dev/null <<'EOF'
[Unit]
Description=Scan upload directory with clamd
After=clamd@scan.service

[Service]
Type=oneshot
ExecStart=/usr/bin/clamdscan --fdpass --infected --move=/var/lib/clamav-quarantine /srv/uploads
SuccessExitStatus=0 1
EOF

sudo tee /etc/systemd/system/clamdscan-uploads.timer > /dev/null <<'EOF'
[Unit]
Description=Hourly upload scan

[Timer]
OnCalendar=hourly
RandomizedDelaySec=10m
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo mkdir -p /var/lib/clamav-quarantine /srv/uploads
sudo systemctl daemon-reload
sudo systemctl enable --now clamdscan-uploads.timer
```

`--infected` keeps the log short (only detections are reported), `--move`
quarantines rather than deletes, and `SuccessExitStatus=0 1` stops systemd
from marking a run that *found* something as a service failure — exit code 1
means detections, which is the timer doing its job.

Check the schedule took:

```
systemctl list-timers clamdscan-uploads.timer
```

## Recovery and false positives

- A quarantined false positive is just a moved file: inspect it in
  `/var/lib/clamav-quarantine` and move it back.
- To exclude a known-good path, add `ExcludePath` lines in
  `/etc/clamd.d/scan.conf` and restart `clamd@scan`.
- If clamd is killed by the OOM killer on a small machine, it logs to the
  journal; the fix is more memory, not retries — the signature set does not
  shrink.

## Notes

- For synchronous scan-on-upload (reject the file before it lands), point
  your application at the clamd socket: most languages have a client for the
  clamd protocol (`INSTREAM`). The timer sweep still matters as defense in
  depth.
- ClamAV catches commodity malware and known signatures, not targeted
  attacks. Treat it as one layer: keep uploads non-executable
  (`noexec` mount option) and outside the web root regardless.
