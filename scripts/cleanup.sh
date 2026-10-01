#!/usr/bin/env bash
set -euo pipefail
builder="cirujano-build-$GITHUB_RUN_ID"
cleanup_failed=0
# Always remove private credentials, even when Docker cleanup cannot be verified.
rm -rf -- "$RUNNER_TEMP/cirujano-build-$GITHUB_RUN_ID" || cleanup_failed=1
timeout --kill-after=5s 60s docker buildx rm "$builder" >/dev/null 2>&1 || true
if ! builders=$(timeout --kill-after=5s 30s docker buildx ls --format '{{.Name}}'); then
  echo owned-builder-cleanup-unverified; cleanup_failed=1
elif printf '%s\n' "$builders" | grep -Fxq "$builder"; then
  echo owned-builder-cleanup-incomplete; cleanup_failed=1
fi
for owned in "cirujano-probe-$GITHUB_RUN_ID" "cirujano-publish-$GITHUB_RUN_ID" "buildx_buildkit_${builder}0"; do
  timeout --kill-after=5s 10s docker rm -f "$owned" >/dev/null 2>&1 || true
  if ! live=$(timeout --kill-after=5s 10s docker ps -a --filter "name=^/$owned$" --format '{{.ID}}'); then
    echo owned-container-cleanup-unverified; cleanup_failed=1
  elif test -n "$live"; then
    echo owned-container-cleanup-incomplete; cleanup_failed=1
  fi
done
# A failed builder removal can leave its state volume after the container is gone.
volume="buildx_buildkit_${builder}0_state"
timeout --kill-after=5s 10s docker volume rm "$volume" >/dev/null 2>&1 || true
if ! volumes=$(timeout --kill-after=5s 10s docker volume ls --filter "name=^$volume$" --format '{{.Name}}'); then
  echo owned-builder-volume-cleanup-unverified; cleanup_failed=1
elif test -n "$volumes"; then
  echo owned-builder-volume-cleanup-incomplete; cleanup_failed=1
fi
exit "$cleanup_failed"
