#!/usr/bin/env bash
set -euo pipefail
umask 077
bash scripts/guard.sh
private="$RUNNER_TEMP/cirujano-build-$GITHUB_RUN_ID"
python3 - "$private/content.json" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['verified'] is True
PY
test -n "$REGISTRY_TOKEN"
owned="cirujano-publish-$GITHUB_RUN_ID"
tool=quay.io/skopeo/stable@sha256:9988d67af5ce59f9045c6f525386e7941775727b0ff2aac7ba498b8adf79053b
registry=cr.eu-north1.nebius.cloud/e00n3hvnajpf75kkc6/optimization-proof
trap 'rm -f "$private/auth.json"; timeout --kill-after=5s 10s docker rm -f "$owned" >/dev/null 2>&1 || true' EXIT
run_tool() {
 timeout --kill-after=5s "$1" docker run --rm -i --name "$owned" --user "$(id -u):$(id -g)" --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,size=128m --mount "type=bind,src=$private,dst=/transfer" "$tool" "${@:2}"
}
printf '%s' "$REGISTRY_TOKEN" | run_tool 35s --command-timeout 30s login --authfile /transfer/auth.json --username iam --password-stdin cr.eu-north1.nebius.cloud >"$private/login.stdout" 2>"$private/login.stderr" || { echo registry-login-failed; exit 1; }
unset REGISTRY_TOKEN
python3 - "$private/auth.json" <<'PYAUTH'
import pathlib,stat,sys
assert stat.S_IMODE(pathlib.Path(sys.argv[1]).stat().st_mode)==0o600
PYAUTH
run_tool 905s --command-timeout 900s --override-os linux --override-arch amd64 copy --quiet --retry-times 0 --image-parallel-copies 1 --dest-authfile /transfer/auth.json --digestfile /transfer/digest.txt docker-archive:/transfer/image.tar "docker://$registry:hosted-41ddfe532242" >"$private/copy.stdout" 2>"$private/copy.stderr" || { echo registry-copy-failed; exit 1; }
digest=$(cat "$private/digest.txt")
[[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
run_tool 65s --command-timeout 60s inspect --raw --authfile /transfer/auth.json "docker://$registry@$digest" >"$private/registry-manifest.json" 2>"$private/readback.stderr"
run_tool 65s --command-timeout 60s inspect --raw --authfile /transfer/auth.json "docker://$registry:hosted-41ddfe532242" >"$private/tag-manifest.json" 2>"$private/tag-readback.stderr"
python3 scripts/verify_publication.py "$private"
cat "$private/receipt.json"
