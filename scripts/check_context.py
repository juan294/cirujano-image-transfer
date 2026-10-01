import pathlib,json,hashlib
root=pathlib.Path(__file__).resolve().parents[1]
expected=json.loads((root/'context-files.json').read_text())
actual=[]
for p in sorted((root/'context').rglob('*')):
 if p.is_symlink():raise ValueError('context-symlink')
 if p.is_file():actual.append({'path':p.relative_to(root/'context').as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
if actual!=expected:raise ValueError('context-drift')
if sum(f['bytes'] for f in actual)>65536:raise ValueError('context-size')
print('reviewed-context-verified')
