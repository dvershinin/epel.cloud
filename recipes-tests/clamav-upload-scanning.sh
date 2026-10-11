#!/usr/bin/env bash
# Mirrors content/recipes/clamav-upload-scanning.md step by step.
set -euxo pipefail

dnf -y install epel-release
dnf -y install clamav clamd clamav-update

echo "=== 2. fetch signatures ==="
freshclam
systemctl enable --now clamav-freshclam

echo "=== 3. configure and start clamd ==="
sed -i 's|^#LocalSocket /run/clamd.scan/clamd.sock|LocalSocket /run/clamd.scan/clamd.sock|' /etc/clamd.d/scan.conf
systemctl enable --now clamd@scan

# Wait for the daemon to finish loading signatures.
for _ in $(seq 1 60); do
  [ -S /run/clamd.scan/clamd.sock ] && break
  sleep 5
done
test -S /run/clamd.scan/clamd.sock

echo "=== verify with EICAR ==="
printf 'X5O!P%%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > /tmp/eicar.txt
set +e
clamdscan --fdpass /tmp/eicar.txt
RC=$?
set -e
[ "$RC" -eq 1 ]  # exit 1 == infected file found
clamdscan --fdpass /tmp/eicar.txt 2>/dev/null | grep -q 'FOUND' || { clamdscan --fdpass /tmp/eicar.txt || true; }

echo "=== 4. upload sweep timer ==="
tee /etc/systemd/system/clamdscan-uploads.service > /dev/null <<'EOF'
[Unit]
Description=Scan upload directory with clamd
After=clamd@scan.service

[Service]
Type=oneshot
ExecStart=/usr/bin/clamdscan --fdpass --infected --move=/var/lib/clamav-quarantine /srv/uploads
SuccessExitStatus=0 1
EOF

tee /etc/systemd/system/clamdscan-uploads.timer > /dev/null <<'EOF'
[Unit]
Description=Hourly upload scan

[Timer]
OnCalendar=hourly
RandomizedDelaySec=10m
Persistent=true

[Install]
WantedBy=timers.target
EOF

mkdir -p /var/lib/clamav-quarantine /srv/uploads
systemctl daemon-reload
systemctl enable --now clamdscan-uploads.timer
systemctl list-timers clamdscan-uploads.timer --no-pager

echo "=== sweep quarantines an infected upload ==="
cp /tmp/eicar.txt /srv/uploads/invoice.pdf.exe
systemctl start clamdscan-uploads.service
ls -l /var/lib/clamav-quarantine/
test -f /var/lib/clamav-quarantine/invoice.pdf.exe
test ! -f /srv/uploads/invoice.pdf.exe

echo "RECIPE OK"
