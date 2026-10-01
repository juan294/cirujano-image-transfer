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
   for name,data in {'registry-manifest.json':raw,'tag-manifest.json':raw,'digest.txt':('sha256:'+hashlib.sha256(raw).hexdigest()).encode(),'image-id':config.encode(),'content.json':b'{"verified":true}'}.items():(p/name).write_bytes(data)
   env=dict(os.environ,GITHUB_REPOSITORY='juan294/cirujano-image-transfer',GITHUB_SHA='b'*40,GITHUB_RUN_ID='123')
   command=['python3','scripts/verify_publication.py',str(p)]
   result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(json.loads((p/'receipt.json').read_text())['configDigest'],config)
   (p/'image-id').write_text('sha256:'+'c'*64)
   result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0)
   self.assertIn('config-digest-mismatch',result.stderr)
   (p/'image-id').write_text(config);(p/'registry-manifest.json').write_bytes(raw+b' ')
   result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0)
   self.assertIn('platform-digest-mismatch',result.stderr)
 def test_publish_success_and_failures_cleanup_auth(self):
  import json,shutil
  for failure in ['', 'copy', 'config']:
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
    p=pathlib.Path(d);private=p/'cirujano-build-123';private.mkdir();binpath=p/'bin';binpath.mkdir()
    shutil.copy(ROOT/'scripts/fake_docker.py',binpath/'docker');(binpath/'docker').chmod(0o700)
    (private/'content.json').write_text('{"verified":true}');(private/'image-id').write_text('sha256:'+'a'*64)
    env=dict(os.environ,PATH=str(binpath)+os.pathsep+os.environ['PATH'],FIXTURE_PRIVATE=str(private),FIXTURE_FAIL=failure,RUNNER_TEMP=d,GITHUB_REPOSITORY='juan294/cirujano-image-transfer',GITHUB_REF='refs/heads/develop',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA='b'*40,APPROVED_COMMIT='b'*40,GITHUB_RUN_ID='123',REGISTRY_TOKEN='fixture-credential')
    result=subprocess.run(['bash','scripts/publish.sh'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
    self.assertEqual(result.returncode==0,not bool(failure),result.stderr)
    self.assertFalse((private/'auth.json').exists())
    calls=[json.loads(line) for line in (private/'calls.jsonl').read_text().splitlines()]
    self.assertEqual(sum('copy' in call for call in calls),1)
    self.assertNotIn('fixture-credential',json.dumps(calls)+result.stdout+result.stderr)
    self.assertEqual((private/'receipt.json').exists(),not bool(failure))
if __name__=='__main__':unittest.main()
