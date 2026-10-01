import {readdir,readFile} from 'node:fs/promises';
import {join} from 'node:path';
export function stripCheckedAt(value) {
  if(Array.isArray(value))return value.map(stripCheckedAt);
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([key])=>key!=='checkedAt').map(([key,item])=>[key,stripCheckedAt(item)]));
  return value;
}
export async function indexIdentity(root,jsonDigest) {
  const indexes={};
  for(const shard of(await readdir(root)).sort())for(const name of(await readdir(join(root,shard))).sort())indexes[shard+'/'+name]=stripCheckedAt(JSON.parse(await readFile(join(root,shard,name),'utf8')));
  return jsonDigest(indexes);
}
