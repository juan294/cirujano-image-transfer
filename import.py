"""One fixed GHCR mirror import with bounded asynchronous readback.
Workflow supplies credentials privately and enforces an outer deadline.
"""
import hashlib,json,os,pathlib,queue,re,tempfile,threading,time,urllib.request,urllib.error,urllib.parse
ORIGIN='https://api.tokenfactory.nebius.com'
PREFIX='/sandboxes/v1/'
UUID=r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}'
class SafeFailure(Exception):pass
def require(ok,code):
 if not ok:raise SafeFailure(code)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(v):return hashlib.sha256(v).hexdigest()
def decode(raw):
 def pairs(items):
  d={}
  for k,v in items:
   require(k not in d and k not in ('__proto__','constructor','prototype'),'invalid-json-key');d[k]=v
  return d
 try:return json.loads(raw.decode('utf8'),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(SafeFailure('invalid-json-number')))
 except SafeFailure:raise
 except Exception:raise SafeFailure('invalid-json') from None
def read_json(path,limit=32*1024*1024):
 p=pathlib.Path(path);require(not p.is_symlink() and p.is_file(),'prerequisite-missing')
 with p.open('rb') as f:raw=f.read(limit+1)
 require(len(raw)<=limit,'prerequisite-size');return decode(raw),digest(raw)
def directory_fsync(directory):
 fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
def exclusive_write(path,value):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
 directory_fsync(pathlib.Path(path).parent)
def save(path,value):
 p=pathlib.Path(path);require(not p.is_symlink(),'unsafe-receipt-path');fd,name=tempfile.mkstemp(prefix='.phase6-import-',dir=p.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
  os.replace(name,p);directory_fsync(p.parent)
 finally:
  if os.path.exists(name):os.unlink(name)
def owned_location(value):
 require(isinstance(value,str),'invalid-location');url=urllib.parse.urljoin(ORIGIN,value);p=urllib.parse.urlsplit(url)
 require(p.scheme=='https' and p.netloc=='api.tokenfactory.nebius.com' and not p.query and not p.fragment and re.fullmatch(PREFIX+'operations/'+UUID,p.path),'invalid-location');return url
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise SafeFailure('redirect-refused')
def native_transport(method,url,headers,body,remaining,maximum):
 require(url.startswith(ORIGIN+PREFIX),'unapproved-origin')
 req=urllib.request.Request(url,data=body,headers=headers,method=method)
 try:response=urllib.request.build_opener(NoRedirect).open(req,timeout=max(.01,remaining))
 except urllib.error.HTTPError as e:response=e
 with response:
  raw=response.read(maximum+1);require(len(raw)<=maximum,'response-size')
  return response.status,{'Location':response.headers.get('Location'),'Retry-After':response.headers.get('Retry-After')},raw

def run_import(request_path,tf_key,cloud_token,transport=None,clock=time.monotonic,sleep=time.sleep):
 receipt={'schemaVersion':1,'kind':'native-image-import-receipt','status':'blocked','reasonCode':'prerequisite-not-confirmed','operationId':None,'operationUrl':None,'imageUuid':None,'posts':0,'costStatus':'unavailable','currency':None,'retention':'owner-retained-one-image','credentialValuesRetained':False}
 sent=False;request=None;deadline=clock()+600
 try:
  request,request_hash,loaded=validate_request(request_path)
  require(all(isinstance(s,str) and 0<len(s)<16384 and not re.search(r'[\x00-\x20\x7f]',s) for s in [tf_key,cloud_token]),'credential-unavailable')
  body=canonical({'registry':{'url':request['registryReference'],'credentials':{'username':'juan294','password':cloud_token}},'timeout':600})
  receipt.update(requestDigest=request_hash,requestHash=digest(body),registryReference=request['registryReference'],identity=request['identity'],project=request['project'])
  intent={**receipt,'status':'intent-recorded','reasonCode':'one-import-reserved','sanitizedRequest':{'registry':{'url':request['registryReference'],'credentials':{'username':'juan294','password':'[REDACTED]'}},'timeout':600}}
  exclusive_write(request['intentPath'],intent)
  headers={'Authorization':'Bearer '+tf_key,'Project':request['project'],'Content-Type':'application/json'};transport=transport or native_transport
  def call(method,url,data=None,maximum=32*1024*1024):
   remaining=deadline-clock();require(remaining>0,'deadline');result=queue.Queue(maxsize=1)
   def worker():
    try:result.put((True,transport(method,url,headers,data,remaining,maximum)))
    except Exception:result.put((False,None))
   threading.Thread(target=worker,daemon=True).start()
   try:ok,value=result.get(timeout=remaining)
   except queue.Empty:raise SafeFailure('deadline') from None
   require(ok,'transport-failed');return value
  receipt['status']='outcome-unknown';sent=True;receipt['posts']=1
  status,h,raw=call('POST',request['endpoint'],body,65536);receipt['httpStatus']=status
  require(status==201,'import-post-http-failed')
  try:
   url=owned_location(h.get('Location'));receipt['operationUrl']=url;receipt['operationId']=url.rsplit('/',1)[1];save(request['receiptPath'],receipt)
  except SafeFailure:pass
  created=decode(raw);uid=created.get('uuid');require(isinstance(uid,str) and re.fullmatch(UUID,uid),'create-uuid-invalid')
  if receipt['operationId'] is None:receipt['operationId']=uid;save(request['receiptPath'],receipt);raise SafeFailure('invalid-location')
  require(receipt['operationId']==uid,'create-location-uuid-drift');save(request['receiptPath'],receipt)
  while True:
   status,h,raw=call('GET',receipt['operationUrl']);require(status==200,'operation-http-failed');operation=decode(raw)
   require(operation.get('uuid')==uid and operation.get('kind')=='image_import' and operation.get('metadata',{}).get('registry',{}).get('url')==request['registryReference'],'operation-identity-drift')
   state=operation.get('status');require(state in ('PENDING','ASSIGNED','EXECUTING','SUCCESS','FAILED','CANCELLED'),'operation-state-invalid');receipt['operationStatus']=state;save(request['receiptPath'],receipt)
   if state in ('FAILED','CANCELLED'):receipt['status']='failed';raise SafeFailure('import-terminal-failed')
   if state=='SUCCESS':break
   delay=h.get('Retry-After');delay=min(5,max(.5,float(delay))) if isinstance(delay,str) and re.fullmatch(r'\d+(?:\.\d+)?',delay) else 2
   require(clock()+delay<deadline,'deadline');sleep(delay)
  image=operation.get('result',{}).get('image');require(isinstance(image,str) and re.fullmatch(UUID,image),'image-uuid-invalid');receipt['imageUuid']=image
  status,_,raw=call('GET',ORIGIN+PREFIX+'inspect/'+image+'/',maximum=65536);require(status==200,'image-inspect-http');inspection=decode(raw);require(inspection.get('uuid')==image and inspection.get('operation_uuid')==uid,'image-inspect-identity')
  expected=loaded['localReadback']['runtimeReadback'];hashes={}
  for name,path in [('manifest','/opt/cirujano/image.json'),('recipe','/opt/cirujano/recipe.json'),('harness','/opt/cirujano/harness.mjs'),('lockfile','/opt/cirujano/dependency-input/pnpm-lock.yaml')]:
   status,_,raw=call('GET',ORIGIN+PREFIX+'inspect/'+image+'/download?'+urllib.parse.urlencode({'path':path}),maximum=524288 if name=='harness' else 4194304 if name=='lockfile' else 65536);require(status==200,'image-download-http')
   require(tf_key.encode() not in raw and cloud_token.encode() not in raw,'credential-in-image')
   hashed=digest(canonical(decode(raw))) if name in ('manifest','recipe') else digest(raw);require(hashed==expected[name+'Hash'],'image-content-drift');hashes[name+'Hash']=hashed
   if name=='manifest':require(decode(raw)==expected['manifest'],'image-manifest-drift')
  receipt.update(status='imported-image-readback-confirmed',reasonCode='import-readback-passed',imageFileHashes=hashes,dependencyStoreHash=expected['dependencyStoreHash'],dependencyStoreVerification='manifest-binding-only; native execution probe still required',retainedImage=True)
 except FileExistsError:receipt.update(status='blocked',reasonCode='existing-import-intent-reconcile-no-repeat')
 except SafeFailure as error:
  receipt['reasonCode']=str(error)
  if sent and receipt['status']!='failed':receipt['status']='outcome-unknown'
 except OSError:receipt.update(status='outcome-unknown' if sent else 'blocked',reasonCode='receipt-durability-failed' if sent else 'intent-durability-failed')
 except Exception:receipt.update(status='outcome-unknown' if sent else 'blocked',reasonCode='import-safe-failure')
 finally:
  tf_key='';cloud_token=''
  if request is not None and sent:
   try:save(request['receiptPath'],receipt)
   except Exception:receipt.update(status='outcome-unknown',reasonCode='receipt-durability-failed')
 return receipt
DIGEST='sha256:e3058fb86a3bf2f4f71fe26bb89c66922837507508f96ddbc369b264833684a0'
CONFIG='sha256:a8f16af135de5328dac235a743335c5127ccb07862e330f7ba2dfe3485f3d141'
DEST='ghcr.io/juan294/cirujano-optimization-proof-mirror:hosted-41ddfe532242'
PROJECT_HASH='0c273dc4004b2ae50f5f325dee3dcc1536b7e134858c8c05d1e265346cd9b128'
def validate_request(path):
 request,request_hash=read_json(path,65536)
 require(request['registryReference']=='docker://'+DEST.split(':')[0]+'@'+DIGEST and digest(request['project'].encode())==PROJECT_HASH,'fixed-recovery-identity')
 require(type(request['maximumImports']) is int and request['maximumImports']==1 and type(request['timeoutSeconds']) is int and request['timeoutSeconds']==600 and request['endpoint']==ORIGIN+PREFIX+'images/import','fixed-recovery-limits')
 directory=pathlib.Path(path).parent
 manifest=(directory/'manifest.json').read_bytes();config=(directory/'config.json').read_bytes()
 require('sha256:'+digest(manifest)==DIGEST and 'sha256:'+digest(config)==CONFIG,'mirror-byte-proof')
 parsed=decode(manifest);require(parsed['config']['digest']==CONFIG and parsed['config']['size']==len(config) and decode(config)['architecture']=='amd64' and decode(config)['os']=='linux','mirror-format')
 expected,_=read_json('expected-image.json',65536)
 require(digest(canonical(expected))=='fd71b7869d40399af00fd64ec4270669c2e29c47685cb4d345fd12c334effdef','expected-image-binding')
 runtime={'manifest':expected,'manifestHash':digest(canonical(expected)),**{k:expected[k] for k in ['recipeHash','harnessHash','lockfileHash','dependencyStoreHash']}}
 return request,request_hash,{'localReadback':{'runtimeReadback':runtime}}
PUBLIC_FIELDS=['status','reasonCode','operationId','imageUuid','posts','httpStatus','operationStatus','imageFileHashes','dependencyStoreHash','dependencyStoreVerification','retainedImage','costStatus','currency']
def export_result():
 p=pathlib.Path('.private-import/receipt.json')
 if not p.is_file() or pathlib.Path('recovery-result.json').exists():return
 result,_=read_json(p,65536);public={k:result.get(k) for k in PUBLIC_FIELDS};public.update(platformManifestDigest=DIGEST,configDigest=CONFIG)
 exclusive_write('recovery-result.json',public)
def main():
 import sys
 if sys.argv[1:]==['--export']:
  export_result();return 0
 require(len(sys.argv)==1,'unsupported-recovery-arguments')
 os.umask(0o077);directory=pathlib.Path('.private-import');directory.mkdir(mode=0o700)
 # Skopeo copies and verifies exact immutable source bytes; no project code runs.
 for name in ['manifest.json','config.json']:(directory/name).write_bytes(pathlib.Path('.private-mirror',name).read_bytes())
 tf_key=os.environ.pop('TOKENFACTORY_KEY');registry_key=os.environ.pop('GITHUB_TOKEN');project=os.environ.pop('TOKENFACTORY_PROJECT')
 request={'registryReference':'docker://'+DEST.split(':')[0]+'@'+DIGEST,'project':project,'maximumImports':1,'timeoutSeconds':600,'endpoint':ORIGIN+PREFIX+'images/import','intentPath':str(directory/'intent.json'),'receiptPath':str(directory/'receipt.json'),'identity':{'platformManifestDigest':DIGEST,'configDigest':CONFIG}}
 exclusive_write(directory/'request.json',request)
 result=run_import(directory/'request.json',tf_key,registry_key);tf_key='';registry_key=''
 public={k:result.get(k) for k in PUBLIC_FIELDS};public.update(platformManifestDigest=DIGEST,configDigest=CONFIG)
 exclusive_write('recovery-result.json',public)
 return 0 if result['status']=='imported-image-readback-confirmed' else 1
if __name__=='__main__':
 import sys
 sys.exit(main())
