#!/usr/bin/env bash
set -euo pipefail
test "$GITHUB_REPOSITORY" = juan294/cirujano-image-transfer
test "$GITHUB_REF" = refs/heads/develop
test "$GITHUB_RUN_ATTEMPT" = 1
test "$GITHUB_SHA" = "$APPROVED_COMMIT"
