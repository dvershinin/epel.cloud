---
title: Stop SSH brute force with fail2ban
slug: fail2ban-ssh
description: Install fail2ban from EPEL on AlmaLinux, Rocky Linux or RHEL 9/10 and ban IPs that hammer sshd, with nftables bans and safe unban commands.
updated: 2026-10-11
last_tested: 2026-10-11
tested_on: AlmaLinux 9.8 and 10.2 systemd containers (aarch64)
releases: [EL 9, EL 10]
arches: [x86_64, aarch64]
time: 15 minutes
weight: 10
ingredients:
  - name: fail2ban 1.1.0
    repo: EPEL
  - name: nftables
    repo: BaseOS
sources:
  - title: fail2ban documentation
    url: https://github.com/fail2ban/fail2ban
  - title: EPEL quickstart
    url: https://docs.fedoraproject.org/en-US/epel/getting-started/
---

Any server with port 22 open collects thousands of password-guessing attempts
per day. `fail2ban` watches authentication logs and tells the firewall to drop
traffic from addresses that keep failing. On Enterprise Linux it reads sshd
events straight from the systemd journal and bans through nftables, the
kernel's native firewall — no extra log files, no iptables legacy layer.

## Prerequisites

- AlmaLinux, Rocky Linux or RHEL 9/10 with root or sudo access.
- EPEL enabled: `sudo dnf install epel-release`
  ([mirror setup](/mirror) if you want faster downloads).

## 1. Install fail2ban

```
sudo dnf install fail2ban
```

## 2. Configure the sshd jail

Never edit `jail.conf`; package updates overwrite it. Local overrides belong
in `jail.local`:

```
sudo tee /etc/fail2ban/jail.local > /dev/null <<'EOF'
[DEFAULT]
# Never ban these addresses. Add your own workstation or VPN.
ignoreip = 127.0.0.1/8 ::1

# Ban via fail2ban's own nftables table. Works the same whether or not
# firewalld is active, and survives firewalld reloads.
banaction = nftables[type=multiport]
banaction_allports = nftables[type=allports]

# How long an offender stays banned.
bantime = 1h
# Repeat offenders get exponentially longer bans, up to a week.
bantime.increment = true
bantime.maxtime = 1w

# Five failures within ten minutes earns a ban.
findtime = 10m
maxretry = 5

[sshd]
enabled = true
EOF
```

On EL 9/10 the sshd jail reads from the systemd journal by default, so this
works on a minimal install with no rsyslog and no `/var/log/secure`.

The EPEL package also installs `fail2ban-firewalld`, which would otherwise
route bans through firewalld rich rules; the explicit `banaction` above keeps
ban behavior identical on every host, firewalld or not. fail2ban's `f2b-table`
is its own nftables table and coexists cleanly with firewalld's rules.

**Put your own IP in `ignoreip` before enabling the service.** A typo'd
password from your own desk five times is enough to lock you out otherwise.

## 3. Start and enable the service

```
sudo systemctl enable --now fail2ban
```

## Verify

Ask the server which jails run and what the sshd jail has seen:

```
sudo fail2ban-client status sshd
```

Expected output on a fresh install:

```
Status for the jail: sshd
|- Filter
|  |- Currently failed:	0
|  |- Total failed:	0
|  `- Journal matches:	_SYSTEMD_UNIT=sshd.service + _COMM=sshd + _COMM=sshd-session
`- Actions
   |- Currently banned:	0
   |- Total banned:	0
   `- Banned IP list:
```

To prove the full pipeline (jail → kernel firewall rule) without waiting for a
real attacker, ban a documentation address by hand and inspect fail2ban's
nftables table:

```
sudo fail2ban-client set sshd banip 203.0.113.42
sudo nft list table inet f2b-table
```

Expected:

```
table inet f2b-table {
	set addr-set-sshd {
		type ipv4_addr
		elements = { 203.0.113.42 }
	}

	chain f2b-chain {
		type filter hook input priority filter - 1; policy accept;
		tcp dport 22 ip saddr @addr-set-sshd reject with icmp port-unreachable
	}
}
```

Then clean up the test ban:

```
sudo fail2ban-client set sshd unbanip 203.0.113.42
```

Within a day on an internet-facing host, `Total banned` starts climbing on its
own; check with `sudo fail2ban-client banned`.

## Recovery: you banned yourself

If you can still reach the machine another way (console, VPN, second IP):

```
sudo fail2ban-client set sshd unbanip YOUR.IP.ADD.RESS
```

If not, use your provider's out-of-band console. Bans do not survive a
fail2ban restart on this setup, so `sudo systemctl restart fail2ban` from the
console also clears the ban table. After recovering, add the address to
`ignoreip` in `jail.local` and run `sudo systemctl reload fail2ban`.

## Notes

- `maxretry = 5` is forgiving. On servers where only keys are allowed,
  tighten to `maxretry = 3` and raise `bantime`.
- fail2ban only reduces log noise and slows password guessing. The real
  fix is `PasswordAuthentication no` in `sshd_config` once every user has keys.
- Watch activity over time with `sudo fail2ban-client banned` or
  `journalctl -u fail2ban`.
