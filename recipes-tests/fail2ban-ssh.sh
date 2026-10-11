#!/usr/bin/env bash
# Mirrors content/recipes/fail2ban-ssh.md step by step.
set -euxo pipefail

dnf -y install epel-release
dnf -y install fail2ban openssh-server nftables

systemctl enable --now sshd

tee /etc/fail2ban/jail.local > /dev/null <<'EOF'
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1
banaction = nftables[type=multiport]
banaction_allports = nftables[type=allports]
bantime = 1h
bantime.increment = true
bantime.maxtime = 1w
findtime = 10m
maxretry = 5

[sshd]
enabled = true
EOF

systemctl enable --now fail2ban
sleep 3

echo "=== fail2ban-client status sshd ==="
fail2ban-client status sshd

echo "=== manual test ban ==="
fail2ban-client set sshd banip 203.0.113.42
sleep 2
echo "=== nft list table inet f2b-table ==="
nft list table inet f2b-table
nft list table inet f2b-table | grep -q '203.0.113.42'
fail2ban-client get sshd banned

echo "=== unban ==="
fail2ban-client set sshd unbanip 203.0.113.42
sleep 1
nft list table inet f2b-table | grep -q '203.0.113.42' && exit 1
fail2ban-client status sshd

echo "RECIPE OK"
