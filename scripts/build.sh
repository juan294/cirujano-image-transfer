#!/usr/bin/env bash
set -euo pipefail
umask 077
bash scripts/guard.sh
python3 scripts/check_context.py
private="$RUNNER_TEMP/cirujano-build-$GITHUB_RUN_ID"
mkdir -m 700 "$private"
timeout --kill-after=10s 1200s docker buildx build --platform linux/amd64 --no-cache --provenance=false --sbom=false --output "type=docker,dest=$private/image.tar" context >"$private/build.stdout" 2>"$private/build.stderr" || { echo build-failed; exit 1; }
timeout --kill-after=5s 120s docker load --input "$private/image.tar" >"$private/load.stdout" 2>"$private/load.stderr"
# The Docker exporter emits one image config; read its immutable ID from the archive.
image=$(python3 - "$private/image.tar" <<'PY'
import tarfile,json,re,sys
with tarfile.open(sys.argv[1]) as t:
 m=json.load(t.extractfile('manifest.json'));assert len(m)==1
 c=m[0]['Config'];match=re.fullmatch(r'(?:blobs/sha256/)?([a-f0-9]{64})(?:\.json)?',c);assert match
 print('sha256:'+match[1])
PY
)
printf '%s' "$image" >"$private/image-id"
test "$(timeout 15s docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image")" = linux/amd64
timeout --kill-after=5s 180s docker run --rm --name "cirujano-probe-$GITHUB_RUN_ID" --platform linux/amd64 --network none --read-only --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 1g --workdir / --mount "type=bind,src=$PWD/scripts/probe.mjs,dst=/probe.mjs,readonly" --entrypoint /usr/local/bin/node "$image" /probe.mjs >"$private/content.json" 2>"$private/probe.stderr" || { echo image-content-verification-failed; exit 1; }
# Pull the fixed publishing tool before any credential is provided.
timeout --kill-after=5s 120s docker pull --platform linux/amd64 quay.io/skopeo/stable@sha256:9988d67af5ce59f9045c6f525386e7941775727b0ff2aac7ba498b8adf79053b >"$private/tool.stdout" 2>"$private/tool.stderr"
echo 'build-and-offline-content-readback-passed'
