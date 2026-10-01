import unittest, subprocess, pathlib, tempfile, os
ROOT=pathlib.Path(__file__).resolve().parents[1]
class BuildTests(unittest.TestCase):
 def setUp(self):
  for name in ['check_context.py','probe.mjs','guard.sh']:
   self.assertTrue((ROOT/'scripts'/name).is_file(),name)
 def test_context_tamper_blocks_build(self):
  with tempfile.TemporaryDirectory() as d:
   import shutil
   clone=pathlib.Path(d)/'repo';shutil.copytree(ROOT,clone,ignore=shutil.ignore_patterns('.git'))
   with (clone/'context/harness.mjs').open('a') as f:f.write('\n// tamper\n')
   p=subprocess.run(['python3','scripts/check_context.py'],cwd=clone,capture_output=True,text=True)
   self.assertNotEqual(p.returncode,0)
 def test_context_accepts_frozen_files(self):
  p=subprocess.run(['python3','scripts/check_context.py'],cwd=ROOT,capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
 def test_guard_accepts_exact_identity(self):
  env=dict(os.environ,GITHUB_REPOSITORY='juan294/cirujano-image-transfer',GITHUB_REF='refs/heads/develop',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA='a'*40,APPROVED_COMMIT='a'*40)
  p=subprocess.run(['bash','scripts/guard.sh'],cwd=ROOT,env=env,capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
 def test_guard_rejects_wrong_commit(self):
  env=dict(os.environ,GITHUB_REPOSITORY='juan294/cirujano-image-transfer',GITHUB_REF='refs/heads/develop',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA='a'*40,APPROVED_COMMIT='b'*40)
  p=subprocess.run(['bash','scripts/guard.sh'],cwd=ROOT,env=env,capture_output=True,text=True)
  self.assertNotEqual(p.returncode,0)
 def test_publication_guard_rejects_rerun_before_secret_use(self):
  env=dict(os.environ,GITHUB_REPOSITORY='juan294/cirujano-image-transfer',GITHUB_REF='refs/heads/develop',GITHUB_RUN_ATTEMPT='2')
  p=subprocess.run(['bash','scripts/guard.sh'],cwd=ROOT,env=env,capture_output=True,text=True)
  self.assertNotEqual(p.returncode,0)
 def test_publication_requires_verified_config_and_digest(self):
  import json,hashlib
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);config='sha256:'+'a'*64;raw=json.dumps({'config':{'digest':config}}).encode()
   for name,data in {'registry-manifest.json':raw,'tag-manifest.json':raw,'digest.txt':('sha256:'+hashlib.sha256(raw).hexdigest()).encode(),'config-digest':config.encode(),'content.json':b'{"verified":true}'}.items():(p/name).write_bytes(data)
   env=dict(os.environ,GITHUB_REPOSITORY='juan294/cirujano-image-transfer',GITHUB_SHA='b'*40,GITHUB_RUN_ID='123')
   command=['python3','scripts/verify_publication.py',str(p)]
   result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(json.loads((p/'receipt.json').read_text())['configDigest'],config)
   (p/'config-digest').write_text('sha256:'+'c'*64)
   result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0)
   self.assertIn('config-digest-mismatch',result.stderr)
   (p/'config-digest').write_text(config);(p/'registry-manifest.json').write_bytes(raw+b' ')
   result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0)
   self.assertIn('platform-digest-mismatch',result.stderr)
 def test_publish_success_and_failures_cleanup_auth(self):
  import json,shutil
  for failure in ['', 'copy', 'config']:
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
    p=pathlib.Path(d);private=p/'cirujano-build-123';private.mkdir();binpath=p/'bin';binpath.mkdir()
    shutil.copy(ROOT/'scripts/fake_docker.py',binpath/'docker');(binpath/'docker').chmod(0o700)
    (private/'content.json').write_text('{"verified":true}');(private/'config-digest').write_text('sha256:'+'a'*64)
    env=dict(os.environ,PATH=str(binpath)+os.pathsep+os.environ['PATH'],FIXTURE_PRIVATE=str(private),FIXTURE_FAIL=failure,RUNNER_TEMP=d,GITHUB_REPOSITORY='juan294/cirujano-image-transfer',GITHUB_REF='refs/heads/develop',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA='b'*40,APPROVED_COMMIT='b'*40,GITHUB_RUN_ID='123',REGISTRY_TOKEN='fixture-credential')
    result=subprocess.run(['bash','scripts/publish.sh'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
    self.assertEqual(result.returncode==0,not bool(failure),result.stderr)
    self.assertFalse((private/'auth.json').exists())
    calls=[json.loads(line) for line in (private/'calls.jsonl').read_text().splitlines()]
    self.assertEqual(sum('copy' in call for call in calls),1)
    self.assertNotIn('fixture-credential',json.dumps(calls)+result.stdout+result.stderr)
    self.assertEqual((private/'receipt.json').exists(),not bool(failure))
 def test_build_selects_container_driver_and_preserves_failures(self):
  import json
  for failure in ['create','bootstrap','build']:
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
    p=pathlib.Path(d);binpath=p/'bin';binpath.mkdir();calls=p/'calls.jsonl'
    script=binpath/'docker'
    script.write_text("#!/usr/bin/env python3\nimport sys,os,json\na=sys.argv[1:]\nwith open(os.environ['FIXTURE_CALLS'],'a') as f:f.write(json.dumps(a)+'\\n')\nstage={'create':'create','inspect':'bootstrap','build':'build'}.get(a[1]) if a[0]=='buildx' else None\nif stage==os.environ['FIXTURE_FAIL']:\n if stage=='build':sys.stderr.write('x'*20000)\n print('native-docker-error-'+stage,file=sys.stderr);sys.exit(1)\n")
    script.chmod(0o700)
    env=dict(os.environ,PATH=str(binpath)+os.pathsep+os.environ['PATH'],FIXTURE_CALLS=str(calls),FIXTURE_FAIL=failure,RUNNER_TEMP=d,GITHUB_REPOSITORY='juan294/cirujano-image-transfer',GITHUB_REF='refs/heads/develop',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA='b'*40,APPROVED_COMMIT='b'*40,GITHUB_RUN_ID='123')
    result=subprocess.run(['bash','scripts/build.sh'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
    self.assertNotEqual(result.returncode,0)
    self.assertIn('native-docker-error-'+failure,result.stderr)
    self.assertLessEqual(len(result.stderr.encode()),16450)
    commands=[json.loads(line) for line in calls.read_text().splitlines()]
    create=commands[0]
    self.assertEqual(create[:2],['buildx','create']);self.assertIn('docker-container',create)
    self.assertIn('image=moby/buildkit@sha256:cec9f139f45e93c5c69c60f8b07cfad9f43f4ef6b6a6cd917527fea5ff2e3dea',create)
    if failure=='build':
     build=commands[-1];self.assertEqual(build[:2],['buildx','build'])
     self.assertEqual(build[build.index('--builder')+1],'cirujano-build-123')
    self.assertTrue(all('login' not in c and 'copy' not in c and 'run' not in c for c in commands))
 def test_cleanup_removes_private_files_and_reports_docker_gaps(self):
  import json
  for failure in ['', 'builder-list', 'builder-left', 'container-list', 'container-left', 'volume-left']:
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
    p=pathlib.Path(d);private=p/'cirujano-build-123';private.mkdir();(private/'auth.json').write_text('{}')
    binpath=p/'bin';binpath.mkdir();calls=p/'calls.jsonl';script=binpath/'docker'
    script.write_text("#!/usr/bin/env python3\nimport sys,os,json\na=sys.argv[1:];failure=os.environ['FIXTURE_FAIL']\nwith open(os.environ['FIXTURE_CALLS'],'a') as f:f.write(json.dumps(a)+'\\n')\nif a[:2]==['buildx','ls']:\n if failure=='builder-list':sys.exit(1)\n print('unrelated-builder');print('cirujano-build-123' if failure=='builder-left' else '')\nelif a[0]=='ps':\n if failure=='container-list':sys.exit(1)\n if failure=='container-left':print('owned-live-id')\nelif a[:2]==['volume','ls'] and failure=='volume-left':print('buildx_buildkit_cirujano-build-1230_state')\n")
    script.chmod(0o700)
    env=dict(os.environ,PATH=str(binpath)+os.pathsep+os.environ['PATH'],FIXTURE_CALLS=str(calls),FIXTURE_FAIL=failure,RUNNER_TEMP=d,GITHUB_RUN_ID='123')
    result=subprocess.run(['bash','scripts/cleanup.sh'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
    self.assertEqual(result.returncode==0,not bool(failure),result.stderr)
    self.assertFalse(private.exists())
    commands=[json.loads(line) for line in calls.read_text().splitlines()]
    self.assertEqual(commands[0],['buildx','rm','cirujano-build-123'])
    self.assertEqual(sum(c[0]=='rm' for c in commands),3)
    self.assertIn(['volume','rm','buildx_buildkit_cirujano-build-1230_state'],commands)
    for command in commands:
     if command[0]=='rm':self.assertIn(command[-1],['cirujano-probe-123','cirujano-publish-123','buildx_buildkit_cirujano-build-1230'])
 def test_loaded_manifest_id_is_distinct_from_config_digest(self):
  import io,tarfile,json,hashlib
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);index='sha256:'+'b'*64;config=json.dumps({'rootfs':{'diff_ids':['sha256:'+'c'*64]}}).encode();digest=hashlib.sha256(config).hexdigest()
   with tarfile.open(p/'image.tar','w') as t:
    for name,data in [(digest+'.json',config),('manifest.json',json.dumps([{'Config':digest+'.json'}]).encode())]:
     entry=tarfile.TarInfo(name);entry.size=len(data);t.addfile(entry,io.BytesIO(data))
   (p/'load.stdout').write_text('Loaded image ID: '+index+'\n')
   binpath=p/'bin';binpath.mkdir();script=binpath/'docker';script.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps([{'+repr('Id')+':'+repr(index)+','+repr('Os')+':'+repr('linux')+','+repr('Architecture')+':'+repr('amd64')+','+repr('RootFS')+':{'+repr('Layers')+':['+repr('sha256:'+'c'*64)+']}}]))\n');script.chmod(0o700)
   env=dict(os.environ,PATH=str(binpath)+os.pathsep+os.environ['PATH'])
   result=subprocess.run(['python3','scripts/inspect_loaded.py',str(p)],cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),index)
   self.assertEqual((p/'config-digest').read_text(),'sha256:'+digest)
   (p/'load.stdout').write_text('Loaded image ID: '+index+'\nLoaded image ID: '+index+'\n')
   result=subprocess.run(['python3','scripts/inspect_loaded.py',str(p)],cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0)
   (p/'load.stdout').write_text('Loaded image ID: '+index+'\n')
   wrong=json.dumps({'rootfs':{'diff_ids':['sha256:'+'d'*64]}}).encode();wd=hashlib.sha256(wrong).hexdigest()
   with tarfile.open(p/'image.tar','w') as t:
    for name,data in [(wd+'.json',wrong),('manifest.json',json.dumps([{'Config':wd+'.json'}]).encode())]:
     entry=tarfile.TarInfo(name);entry.size=len(data);t.addfile(entry,io.BytesIO(data))
   result=subprocess.run(['python3','scripts/inspect_loaded.py',str(p)],cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0);self.assertIn('loaded-rootfs-drift',result.stderr)
 def test_index_identity_ignores_only_checked_at(self):
  code="import assert from 'node:assert/strict';import {stripCheckedAt} from './scripts/index_identity.mjs';const a={files:{entry:{checkedAt:1,integrity:'abc',size:3}}};const b={files:{entry:{checkedAt:2,integrity:'abc',size:3}}};assert.deepEqual(stripCheckedAt(a),stripCheckedAt(b));b.files.entry.integrity='def';assert.notDeepEqual(stripCheckedAt(a),stripCheckedAt(b));"
  result=subprocess.run(['node','--input-type=module','-e',code],cwd=ROOT,capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
if __name__=='__main__':unittest.main()
