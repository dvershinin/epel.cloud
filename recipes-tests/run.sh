#!/usr/bin/env bash
# Execute one recipe's commands end to end in a clean systemd container.
#
# Usage: recipes-tests/run.sh <slug> [docker platform, default linux/arm64]
#
# Evidence (full transcript) lands in evidence/recipes/<slug>-<arch>-<date>.log.
# Exit status is the recipe script's exit status.
set -euo pipefail

SLUG="${1:?usage: run.sh <slug> [platform]}"
PLATFORM="${2:-linux/arm64}"
IMAGE="${IMAGE:-almalinux/9-init}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
SCRIPT="$HERE/$SLUG.sh"
[ -f "$SCRIPT" ] || { echo "no test script: $SCRIPT" >&2; exit 2; }

ARCH="${PLATFORM##*/}"
OSTAG="el$(echo "$IMAGE" | grep -oE '[0-9]+' | head -1)"
STAMP="$(date +%Y-%m-%d)"
LOG_DIR="$ROOT/evidence/recipes"
LOG="$LOG_DIR/$SLUG-$OSTAG-$ARCH-$STAMP.log"
mkdir -p "$LOG_DIR"

NAME="epelcloud-test-$SLUG-$OSTAG-$ARCH"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --rm --privileged --platform "$PLATFORM" --name "$NAME" \
  -v "$SCRIPT:/recipe-test.sh:ro" "$IMAGE" >/dev/null

# Wait for systemd to finish booting inside the container.
for _ in $(seq 1 60); do
  state="$(docker exec "$NAME" systemctl is-system-running 2>/dev/null || true)"
  case "$state" in running|degraded) break ;; esac
  sleep 2
done

{
  echo "# recipe test: $SLUG"
  echo "# image: $IMAGE  platform: $PLATFORM  date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  docker exec "$NAME" cat /etc/almalinux-release
  echo "# ---"
} | tee "$LOG"

set +e
docker exec "$NAME" bash /recipe-test.sh 2>&1 | tee -a "$LOG"
STATUS=${PIPESTATUS[0]}
set -e

docker rm -f "$NAME" >/dev/null 2>&1 || true
echo "# exit status: $STATUS" | tee -a "$LOG"
exit "$STATUS"
