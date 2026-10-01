import pathlib,json,os,sys,hashlib,re
p=pathlib.Path(sys.argv[1]);raw=(p/'registry-manifest.json').read_bytes();m=json.loads(raw)
digest=(p/'digest.txt').read_text().strip()
if not re.fullmatch('sha256:[a-f0-9]{64}',digest):raise ValueError('invalid-platform-digest')
if digest!='sha256:'+hashlib.sha256(raw).hexdigest():raise ValueError('platform-digest-mismatch')
if (p/'tag-manifest.json').read_bytes()!=raw:raise ValueError('tag-manifest-mismatch')
if m['config']['digest']!=(p/'config-digest').read_text():raise ValueError('config-digest-mismatch')
content=json.loads((p/'content.json').read_text())
if content['verified'] is not True:raise ValueError('contents-not-verified')
receipt={'schemaVersion':1,'kind':'hosted-build-publication','repository':os.environ['GITHUB_REPOSITORY'],'commit':os.environ['GITHUB_SHA'],'runId':os.environ['GITHUB_RUN_ID'],'attempt':1,'platformDigest':digest,'configDigest':m['config']['digest'],'content':content,'registryManifestReadback':True,'nativeImportApproved':False}
(p/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
