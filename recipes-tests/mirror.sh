#!/usr/bin/env bash
# Mirrors content/mirror.md: point dnf at epel.cloud and prove installs work
# with signature verification against the stock Fedora EPEL keys.
set -euxo pipefail

echo "=== step 1: enable EPEL ==="
dnf -y install epel-release

echo "=== step 2: point the repo at epel.cloud ==="
sed -i \
  -e 's|^metalink=|#metalink=|' \
  -e 's|^#baseurl=https://download.example/pub|baseurl=https://epel.cloud/pub|' \
  /etc/yum.repos.d/epel.repo
grep -E '^(baseurl|#metalink)' /etc/yum.repos.d/epel.repo | head -6

dnf --disablerepo='*' --enablerepo=epel makecache

echo "=== step 3: verify ==="
dnf repoinfo epel | grep -E 'Repo-baseurl|Repo-pkgs'
dnf repoinfo epel | grep 'Repo-baseurl' | grep -q 'https://epel.cloud/pub/epel/'

echo "=== install through the mirror (imports the EPEL GPG key) ==="
dnf -y install htop
htop --version | head -1

echo "=== manual signature verification ==="
cd /tmp
dnf -y download htop
ls -l htop-*.rpm
rpm -K htop-*.rpm
rpm -K htop-*.rpm | grep -q 'digests signatures OK'

echo "RECIPE OK"
