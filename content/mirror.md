---
title: Use the mirror
description: Point dnf at epel.cloud, a Cloudflare-cached EPEL mirror, for faster metadata refresh and package downloads on RHEL, AlmaLinux and Rocky Linux.
updated: 2026-10-11
---

## What this mirror is

epel.cloud serves the [EPEL](https://docs.fedoraproject.org/en-US/epel/) package
repositories through Cloudflare's global edge cache. Requests under
`/pub/epel/` are fetched from Fedora's own download servers and cached close to
you. RPM bytes, repository metadata and GPG signatures pass through unchanged:
`gpgcheck=1` verifies packages against the same Fedora EPEL keys as always.

What that buys you in practice:

- **Nearby downloads.** Cloudflare serves cached packages from a point of
  presence near your servers instead of a distant mirror.
- **Fresh metadata.** Edge-cached repository metadata is invalidated when
  upstream publishes new metadata, so `dnf makecache` sees new packages
  promptly. Successful responses cache for up to 31 days; error responses are
  never cached.
- **No accounts, no tokens.** It is a plain HTTPS mirror. Nothing about your
  package manager configuration changes except the URL.

EPEL 8, 9 and 10 are served live. EPEL 7 reached end of life in June 2024;
requests under `/pub/epel/7/` redirect to the
[Fedora archives](https://archives.fedoraproject.org/pub/archive/epel/7/),
and the archived tree is also reachable at `archive.epel.cloud/pub/archive/epel/7/`.

## Step 1: enable EPEL

On AlmaLinux and Rocky Linux the `epel-release` package comes from the
distribution's own repositories and installs both the repo definition and the
Fedora EPEL GPG keys:

```
sudo dnf install epel-release
```

On RHEL, install the release package for your major version directly from the
mirror (also available from Fedora), and enable CodeReady Builder, which many
EPEL packages depend on:

```
sudo dnf install https://epel.cloud/pub/epel/epel-release-latest-9.noarch.rpm
sudo subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms
```

## Step 2: point the repo at epel.cloud

The stock `epel.repo` uses a `metalink=` line that picks a Fedora mirror for
you. Comment it out and set `baseurl=` to epel.cloud instead:

```
sudo sed -i \
  -e 's|^metalink=|#metalink=|' \
  -e 's|^#baseurl=https://download.example/pub|baseurl=https://epel.cloud/pub|' \
  /etc/yum.repos.d/epel.repo
```

This flips every section of the file (`epel`, `epel-debuginfo`, `epel-source`),
because the commented `baseurl` template is the same in each. `$releasever`
and `$basearch` expand per machine, so the same edit works on EL8, EL9 and
EL10, x86_64 and aarch64.

Then rebuild the cache:

```
sudo dnf --disablerepo='*' --enablerepo=epel makecache
```

## Step 3: verify

Confirm dnf now resolves the repository to epel.cloud:

```
dnf repoinfo epel | grep -E 'Repo-baseurl|Repo-pkgs'
```

Expected output (package count varies as EPEL moves; `$basearch` expands per
machine):

```
Repo-pkgs          : 26542
Repo-baseurl       : https://epel.cloud/pub/epel/9/Everything/aarch64/
```

Now install something through the mirror. On the first EPEL install dnf
imports the Fedora EPEL GPG key (from the file `epel-release` placed under
`/etc/pki/rpm-gpg/`) and verifies the package signature against it:

```
sudo dnf install htop
```

With the key imported, you can also verify any downloaded RPM by hand:

```
dnf download htop
rpm -K htop-*.rpm
```

Expected: `htop-3.3.0-1.el9.aarch64.rpm: digests signatures OK`.
(Run `rpm -K` after at least one EPEL install — before the key import it
reports `SIGNATURES NOT OK` simply because rpm has no key to check against.)

## Reverting

The edit above only comments lines out, so reverting is the mirror image:

```
sudo sed -i \
  -e 's|^#metalink=|metalink=|' \
  -e 's|^baseurl=https://epel.cloud/pub|#baseurl=https://download.example/pub|' \
  /etc/yum.repos.d/epel.repo
sudo dnf clean metadata
```

Or simply reinstall the pristine repo file: `sudo dnf reinstall epel-release`.

## Fair use and guarantees

This is an independent free mirror, not an official Fedora service and not a
contracted CDN. It is operated on a best-effort basis; for
production-critical availability guarantees, keep the default metalink
configuration as your documented fallback. Mirror traffic is never inspected
beyond ordinary web server logs, and nothing here requires registration.
