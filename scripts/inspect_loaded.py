import pathlib,tarfile,json,re,hashlib,subprocess,sys
p=pathlib.Path(sys.argv[1])
match=re.fullmatch(r'Loaded image ID: (sha256:[a-f0-9]{64})\n?',(p/'load.stdout').read_text())
if not match:raise ValueError('ambiguous-loaded-image')
image=match[1]
with tarfile.open(p/'image.tar') as t:
 m=json.load(t.extractfile('manifest.json'))
 if len(m)!=1:raise ValueError('multiple-exported-images')
 c=m[0]['Config'];match=re.fullmatch(r'(?:blobs/sha256/)?([a-f0-9]{64})(?:\.json)?',c)
 if not match:raise ValueError('invalid-config-path')
 member=t.getmember(c)
 if member.size>1048576:raise ValueError('config-too-large')
 raw=t.extractfile(member).read();digest='sha256:'+hashlib.sha256(raw).hexdigest()
 if digest!='sha256:'+match[1]:raise ValueError('archive-config-drift')
 config=json.loads(raw)
inspection=json.loads(subprocess.check_output(['docker','image','inspect',image],timeout=15))
if len(inspection)!=1:raise ValueError('ambiguous-image-inspection')
i=inspection[0]
if i['Id']!=image or i['Os']!='linux' or i['Architecture']!='amd64':raise ValueError('loaded-image-identity')
if i['RootFS']['Layers']!=config['rootfs']['diff_ids']:raise ValueError('loaded-rootfs-drift')
(p/'config-digest').write_text(digest)
(p/'runtime-image-id').write_text(image)
print(image)
