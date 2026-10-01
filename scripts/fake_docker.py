#!/usr/bin/env python3
# Offline test fixture for the external Docker/Skopeo interface.
import os,sys,pathlib,json,hashlib
args=sys.argv[1:];root=pathlib.Path(os.environ['FIXTURE_PRIVATE'])
with (root/'calls.jsonl').open('a') as f:f.write(json.dumps(args)+'\n')
if args[0]=='rm':raise SystemExit(0)
if 'login' in args:
 token=sys.stdin.read();assert token=='fixture-credential'
 (root/'auth.json').write_text('{}');(root/'auth.json').chmod(0o600)
elif 'copy' in args:
 if os.environ.get('FIXTURE_FAIL')=='copy':raise SystemExit(1)
 config=(root/'image-id').read_text()
 if os.environ.get('FIXTURE_FAIL')=='config':config='sha256:'+'c'*64
 raw=json.dumps({'config':{'digest':config}},separators=(',',':')).encode()
 (root/'fixture-manifest.json').write_bytes(raw)
 (root/'digest.txt').write_text('sha256:'+hashlib.sha256(raw).hexdigest())
elif 'inspect' in args:sys.stdout.buffer.write((root/'fixture-manifest.json').read_bytes())
else:raise SystemExit('unexpected-docker-command')
