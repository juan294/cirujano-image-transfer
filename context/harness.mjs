import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { chmod, chown, cp, lstat, mkdir, open, readdir, realpath, writeFile } from 'node:fs/promises';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const LIMIT=16*1024*1024,OUTPUT=1024*1024;
const digest=/^[a-f0-9]{64}$/,sha=/^[a-f0-9]{40}$/,version=/^\d+\.\d+\.\d+$/;
export function canonicalJson(value,depth=0) {
 if(depth>64) throw Error('harness-json-depth');
 if(value===null||typeof value==='boolean'||typeof value==='string') return JSON.stringify(value);
 if(typeof value==='number'&&Number.isFinite(value)) return JSON.stringify(value);
 if(Array.isArray(value)) return `[${value.map(item=>canonicalJson(item,depth+1)).join(',')}]`;
 if(!value||typeof value!=='object'||![Object.prototype,null].includes(Object.getPrototypeOf(value))) throw Error('harness-json-value');
 return `{${Object.keys(value).sort().map(key=>{if(['__proto__','constructor','prototype'].includes(key)) throw Error('harness-json-key');return `${JSON.stringify(key)}:${canonicalJson(value[key],depth+1)}`;}).join(',')}}`;
}
export function sha256(value) {return createHash('sha256').update(value).digest('hex');}
export function jsonDigest(value) {return sha256(canonicalJson(value));}
export function executionCommands(profile) {return [['pnpm','install','--frozen-lockfile'],...profile.commands];}
/** Independent duplicate-key grammar; JSON.parse alone silently loses this evidence. */
export function parseStrictJson(source,limit=LIMIT) {
 if(typeof source!=='string'||Buffer.byteLength(source)>limit) throw Error('harness-json-size');let cursor=0;
 const whitespace=()=>{while(cursor<source.length&&/[ \r\n\t]/.test(source[cursor])) cursor++;};
 const string=()=>{const start=cursor++;while(cursor<source.length){const character=source[cursor++];if(character==='\\') cursor++;else if(character==='"') return JSON.parse(source.slice(start,cursor));}throw Error('harness-json-string');};
 function value(depth) {
  if(depth>64) throw Error('harness-json-depth');whitespace();const character=source[cursor];
  if(character==='{') {cursor++;whitespace();const keys=new Set();if(source[cursor]==='}') {cursor++;return;}while(cursor<source.length){whitespace();if(source[cursor]!=='"') throw Error('harness-json-key');const key=string();if(keys.has(key)||['__proto__','constructor','prototype'].includes(key)) throw Error('harness-json-duplicate-key');keys.add(key);whitespace();if(source[cursor++]!==':') throw Error('harness-json-colon');value(depth+1);whitespace();const delimiter=source[cursor++];if(delimiter==='}') return;if(delimiter!==',') throw Error('harness-json-delimiter');}}
  else if(character==='[') {cursor++;whitespace();if(source[cursor]===']'){cursor++;return;}while(cursor<source.length){value(depth+1);whitespace();const delimiter=source[cursor++];if(delimiter===']') return;if(delimiter!==',') throw Error('harness-json-delimiter');}}
  else if(character==='"') {string();return;}
  else {const token=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(source.slice(cursor));if(token){cursor+=token[0].length;return;}}
  throw Error('harness-json-value');
 }
 value(0);whitespace();if(cursor!==source.length) throw Error('harness-json-trailing');const parsed=JSON.parse(source);canonicalJson(parsed);return parsed;
}
function object(value,keys) {if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join('|')!==[...keys].sort().join('|')) throw Error('harness-object-fields');return value;}
function requireMatch(value,pattern,reason) {if(typeof value!=='string'||!pattern.test(value)) throw Error(reason);}
function boundedText(value) {if(typeof value!=='string'||!value||Buffer.byteLength(value)>8192||/[\u0000-\u001f\u007f]/.test(value)) throw Error('harness-text');}
export function safePath(path) {boundedText(path);if(Buffer.byteLength(path)>512||isAbsolute(path)||path.includes('\\')||/^[A-Za-z]:/.test(path)||path.split('/').some(part=>!part||part==='.'||part==='..')) throw Error('harness-unsafe-path');return path;}
function sensitive(path) {return /(?:^|\/)(?:\.env(?:\..*)?|\.npmrc|\.git|credentials(?:\..*)?|id_rsa|id_ed25519|[^/]*\.(?:pem|key))$/.test(path);}
function integer(value) {if(!Number.isSafeInteger(value)||value<0) throw Error('harness-counter');}
function decodeProfile(value) {
 object(value,['schemaVersion','commands','testReportPath','coverageReportPath','nodeVersion','pnpmVersion','timeoutSeconds','sourcePaths']);
 if(value.schemaVersion!==1||!Array.isArray(value.commands)||!value.commands.length||value.commands.length>100||value.timeoutSeconds!==600) throw Error('harness-profile');
 safePath(value.testReportPath);safePath(value.coverageReportPath);if(sensitive(value.testReportPath)||sensitive(value.coverageReportPath)) throw Error('harness-report-path');
 requireMatch(value.nodeVersion,version,'harness-node-version');requireMatch(value.pnpmVersion,version,'harness-pnpm-version');
 if(!Array.isArray(value.sourcePaths)||new Set(value.sourcePaths).size!==value.sourcePaths.length) throw Error('harness-profile-paths');value.sourcePaths.forEach(safePath);
 for(const command of value.commands){if(!Array.isArray(command)||!command.length||command.length>100||!['node','pnpm'].includes(command[0])||(command[0]==='pnpm'&&['install','i'].includes(command[1]))) throw Error('harness-unsupported-command');command.forEach(boundedText);}
 return value;
}
export function decodeQuality(value) {
 object(value,['commandDigest','tests','coverage']);requireMatch(value.commandDigest,digest,'harness-command-digest');
 if(!Array.isArray(value.tests)||!value.tests.length||value.tests.length>10000||!Array.isArray(value.coverage)||!value.coverage.length||value.coverage.length>5000) throw Error('harness-quality');
 const ids=new Set(),paths=new Set();
 for(const test of value.tests){object(test,['id','outcome']);boundedText(test.id);if(ids.has(test.id)||!['passed','failed','skipped'].includes(test.outcome)) throw Error('harness-test-identity');ids.add(test.id);}
 const counters=['statements','coveredStatements','branches','coveredBranches','functions','coveredFunctions','lines','coveredLines'];
 for(const coverage of value.coverage){object(coverage,['path',...counters]);safePath(coverage.path);if(paths.has(coverage.path)) throw Error('harness-coverage-duplicate');paths.add(coverage.path);counters.forEach(key=>integer(coverage[key]));for(const field of ['Statements','Branches','Functions','Lines']) if(coverage[`covered${field}`]>coverage[field.toLowerCase()]) throw Error('harness-coverage-counters');}
 return value;
}
function verifyQuality(actual,expected) {
 if(actual.commandDigest!==expected.commandDigest||actual.tests.some(test=>test.outcome==='failed')) throw Error('harness-quality-failed');
 const sort=(values,key)=>[...values].sort((a,b)=>a[key]<b[key]?-1:a[key]>b[key]?1:0);
 if(canonicalJson(sort(actual.tests,'id'))!==canonicalJson(sort(expected.tests,'id'))) throw Error('harness-test-inventory-drift');
 const a=sort(actual.coverage,'path'),b=sort(expected.coverage,'path');if(a.length!==b.length) throw Error('harness-coverage-inventory-drift');
 for(let index=0;index<a.length;index++){if(a[index].path!==b[index].path) throw Error('harness-coverage-inventory-drift');for(const field of ['Statements','Branches','Functions','Lines']) if(a[index][field.toLowerCase()]!==b[index][field.toLowerCase()]||a[index][`covered${field}`]<b[index][`covered${field}`]) throw Error('harness-coverage-regression');}
}
export function validatePayload(payload) {
 canonicalJson(payload);if(Buffer.byteLength(canonicalJson(payload))>LIMIT) throw Error('harness-payload-size');
 object(payload,['schemaVersion','kind','role','profileDigest','proposalDigest','toolSourceSha','bundleDigest','imageManifestHash','harnessHash','sourceDigest','workflowPath','workflowHash','files','verificationProfile','expectedQuality']);
 if(payload.schemaVersion!==1||payload.kind!=='sandbox-payload'||!['base','candidate'].includes(payload.role)) throw Error('harness-payload-kind');
 for(const key of ['profileDigest','proposalDigest','bundleDigest','imageManifestHash','harnessHash','sourceDigest','workflowHash']) requireMatch(payload[key],digest,'harness-digest');requireMatch(payload.toolSourceSha,sha,'harness-tool-sha');safePath(payload.workflowPath);
 const profile=decodeProfile(payload.verificationProfile),expected=decodeQuality(payload.expectedQuality);if(expected.commandDigest!==jsonDigest(executionCommands(profile))||expected.tests.some(test=>test.outcome==='failed')) throw Error('harness-profile-quality-drift');
 if(!Array.isArray(payload.files)||!payload.files.length||payload.files.length>5000) throw Error('harness-files');let total=0;const paths=new Set();
 for(const file of payload.files){object(file,['path','mode','hash','bytesBase64']);safePath(file.path);if(sensitive(file.path)||file.path.split('/').includes('.git')||['.home','.pnpm-store'].includes(file.path.split('/')[0])||paths.has(file.path)||!['100644','100755'].includes(file.mode)) throw Error('harness-unsafe-source');paths.add(file.path);requireMatch(file.hash,digest,'harness-file-hash');if(typeof file.bytesBase64!=='string'||! /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(file.bytesBase64)) throw Error('harness-base64');const bytes=Buffer.from(file.bytesBase64,'base64');total+=bytes.length;if(bytes.length>4*1024*1024||total>LIMIT||bytes.toString('base64')!==file.bytesBase64||sha256(bytes)!==file.hash) throw Error('harness-source-hash');}
 for(const path of paths) for(let depth=1;depth<path.split('/').length;depth++) if(paths.has(path.split('/').slice(0,depth).join('/'))) throw Error('harness-source-prefix-collision');
 if(paths.has(profile.testReportPath)||paths.has(profile.coverageReportPath)) throw Error('harness-preseeded-quality-report');
 const metadata=payload.files.map(({path,mode,hash})=>({path,mode,hash})).sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
 if(jsonDigest(metadata)!==payload.sourceDigest||payload.files.find(file=>file.path===payload.workflowPath)?.hash!==payload.workflowHash||profile.sourcePaths.some(path=>!paths.has(path))) throw Error('harness-source-drift');
 return payload;
}
async function regularRead(path,limit=OUTPUT) {
 const handle=await open(path,constants.O_RDONLY|constants.O_NOFOLLOW);
 try {const stat=await handle.stat();if(!stat.isFile()||stat.size>limit) throw Error('harness-report-not-regular-or-size');const data=await handle.readFile();if(data.length>limit) throw Error('harness-report-size');return data;} finally {await handle.close();}
}
async function noSymlinkAncestors(root,path) {let current=root;for(const segment of safePath(path).split('/').slice(0,-1)){current=join(current,segment);const stat=await lstat(current);if(!stat.isDirectory()||stat.isSymbolicLink()) throw Error('harness-path-symlink');}}
export async function dependencyStoreDigest(root) {
 const rootStat=await lstat(root);if(!rootStat.isDirectory()||rootStat.isSymbolicLink()) throw Error('harness-store-path');const files=[];let bytes=0;
 async function walk(directory,prefix='') {for(const name of (await readdir(directory)).sort()){const path=prefix?`${prefix}/${name}`:name;safePath(path);const absolute=join(directory,name),stat=await lstat(absolute);if(stat.isSymbolicLink()) throw Error('harness-store-symlink');if(stat.isDirectory()) await walk(absolute,path);else if(stat.isFile()){bytes+=stat.size;if(bytes>1024*1024*1024||files.length>=100000) throw Error('harness-store-limit');files.push({path,hash:sha256(await regularRead(absolute,1024*1024*1024))});}else throw Error('harness-store-file-type');}}
 await walk(root);files.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);return jsonDigest(files);
}
function execute(executable,args,workspace,env,timeout,identity) {
 return new Promise(resolveResult=>{
  const child=spawn(executable,args,{cwd:workspace,env,shell:false,stdio:['ignore','pipe','pipe'],detached:process.platform!=='win32',...(identity??{})});let timedOut=false,truncated=false,stdout=Buffer.alloc(0),stderr=Buffer.alloc(0),finished=false;
  const terminate=()=>{try{if(process.platform!=='win32'&&child.pid) process.kill(-child.pid,'SIGKILL');else child.kill('SIGKILL');}catch{child.kill('SIGKILL');}};
  const timer=setTimeout(()=>{timedOut=true;terminate();},timeout);
  const capture=(stream,part)=>{const previous=stream==='stdout'?stdout:stderr,combined=Buffer.concat([previous,part]);if(combined.length>OUTPUT){truncated=true;terminate();}if(stream==='stdout') stdout=combined.subarray(0,OUTPUT);else stderr=combined.subarray(0,OUTPUT);};
  child.stdout.on('data',part=>capture('stdout',part));child.stderr.on('data',part=>capture('stderr',part));
  const finish=(exitCode,signal)=>{if(finished) return;finished=true;clearTimeout(timer);resolveResult({exitCode,signal,timedOut,truncated,stdout,stderr});};
  child.on('error',()=>finish(null,'SPAWN_ERROR'));child.on('close',(code,signal)=>finish(code,signal));
 });
}
/** options is a local inert-fixture boundary; the deployed CLI never accepts path overrides. */
export async function runHarness(payload,options={}) {
 const started=Date.now();validatePayload(payload);
 const inertFixture=Object.keys(options).length>0;
 if(!inertFixture&&(process.platform!=='linux'||process.getuid()!==0)) throw Error('harness-root-linux-required');
 const identity={uid:inertFixture?(options.childUid??65534):65534,gid:inertFixture?(options.childGid??65534):65534};
 if(!Number.isSafeInteger(identity.uid)||identity.uid<0||!Number.isSafeInteger(identity.gid)||identity.gid<0) throw Error('harness-child-identity');
 const workspace=options.workspace??'/workspace',store=options.storePath??'/opt/cirujano/store',manifestPath=options.imageManifestPath??'/opt/cirujano/image.json',harnessPath=options.harnessPath??'/opt/cirujano/harness.mjs';
 if(!isAbsolute(workspace)||await realpath(workspace)!==resolve(workspace)||(await readdir(workspace)).length) throw Error('harness-workspace-not-empty-or-symlink');
 const manifest=parseStrictJson((await regularRead(manifestPath)).toString('utf8'));
 object(manifest,['schemaVersion','kind','toolSourceSha','bundleDigest','nodeVersion','pnpmVersion','lockfileHash','dependencyStoreHash','harnessHash','recipeHash']);
 if(manifest.schemaVersion!==1||manifest.kind!=='optimization-image') throw Error('harness-image-manifest');for(const field of ['bundleDigest','lockfileHash','dependencyStoreHash','harnessHash','recipeHash']) requireMatch(manifest[field],digest,'harness-image-digest');requireMatch(manifest.toolSourceSha,sha,'harness-image-tool');
 const profile=payload.verificationProfile;
 if(jsonDigest(manifest)!==payload.imageManifestHash||manifest.harnessHash!==payload.harnessHash||sha256(await regularRead(harnessPath))!==payload.harnessHash||manifest.toolSourceSha!==payload.toolSourceSha||manifest.bundleDigest!==payload.bundleDigest||manifest.nodeVersion!==profile.nodeVersion||manifest.pnpmVersion!==profile.pnpmVersion||manifest.lockfileHash!==payload.files.find(file=>file.path==='pnpm-lock.yaml')?.hash||await dependencyStoreDigest(store)!==manifest.dependencyStoreHash) throw Error('harness-image-drift');
 const executables=options.executables??{node:'/usr/local/bin/node',pnpm:'/usr/local/bin/pnpm'};
 const env={HOME:join(workspace,'.home'),PATH:'/usr/local/bin:/usr/bin:/bin',CI:'true',PNPM_CONFIG_OFFLINE:'true',PNPM_CONFIG_STORE_DIR:store};
 for(const name of ['node','pnpm']) {if(typeof executables[name]!=='string'||!isAbsolute(executables[name])) throw Error('harness-executable');const result=await execute(executables[name],['--version'],workspace,env,10000);if(result.exitCode!==0||result.signal||result.timedOut||result.truncated||result.stdout.toString('utf8').trim()!==`${name==='node'?'v':''}${profile[name==='node'?'nodeVersion':'pnpmVersion']}`) throw Error('harness-runtime-version');}
 await chmod(workspace,0o700);
 for(const file of payload.files){const destination=join(workspace,file.path);await mkdir(dirname(destination),{recursive:true,mode:0o700});await noSymlinkAncestors(workspace,file.path);await writeFile(destination,Buffer.from(file.bytesBase64,'base64'),{mode:file.mode==='100755'?0o700:0o600,flag:'wx'});}
 await mkdir(env.HOME,{mode:0o700});const writableStore=join(workspace,'.pnpm-store');await cp(store,writableStore,{recursive:true,errorOnExist:true,force:false});env.PNPM_CONFIG_STORE_DIR=writableStore;
 async function sourceOwnership(path) {const stat=await lstat(path);if(stat.isSymbolicLink()||(!stat.isFile()&&!stat.isDirectory())) throw Error('harness-workspace-file-type');if(stat.isDirectory()) for(const name of await readdir(path)) await sourceOwnership(join(path,name));await chown(path,identity.uid,identity.gid);await chmod(path,stat.isDirectory()||stat.mode&0o111?0o700:0o600);}
 await sourceOwnership(workspace);const commands=[];let successful=true;const deadline=started+Math.min(options.timeoutMs??600000,600000);
 for(const argv of executionCommands(profile)){const remaining=deadline-Date.now();if(remaining<=0) throw Error('harness-total-timeout');const result=await execute(executables[argv[0]],argv.slice(1),workspace,env,remaining,identity);commands.push({argv,exitCode:result.exitCode,signal:result.signal,timedOut:result.timedOut,truncated:result.truncated,stdoutHash:sha256(result.stdout),stderrHash:sha256(result.stderr)});if(result.exitCode!==0||result.signal||result.timedOut||result.truncated){successful=false;break;}}
 let quality=null;
 if(successful){await noSymlinkAncestors(workspace,profile.testReportPath);await noSymlinkAncestors(workspace,profile.coverageReportPath);const tests=object(parseStrictJson((await regularRead(join(workspace,profile.testReportPath))).toString('utf8')),['tests']),coverage=object(parseStrictJson((await regularRead(join(workspace,profile.coverageReportPath))).toString('utf8')),['coverage']);quality=decodeQuality({commandDigest:jsonDigest(executionCommands(profile)),tests:tests.tests,coverage:coverage.coverage});verifyQuality(quality,payload.expectedQuality);}
 return {schemaVersion:1,kind:'harness-result',role:payload.role,profileDigest:payload.profileDigest,proposalDigest:payload.proposalDigest,toolSourceSha:payload.toolSourceSha,bundleDigest:payload.bundleDigest,imageManifestHash:payload.imageManifestHash,harnessHash:payload.harnessHash,sourceDigest:payload.sourceDigest,workflowHash:payload.workflowHash,commands,quality,elapsedMs:Date.now()-started};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
 try {let input=Buffer.alloc(0);for await(const part of process.stdin){input=Buffer.concat([input,part]);if(input.length>LIMIT) throw Error('harness-stdin-size');}const result=await runHarness(parseStrictJson(input.toString('utf8')));const output=canonicalJson(result);if(Buffer.byteLength(output)>OUTPUT) throw Error('harness-result-size');process.stdout.write(output+'\n');}
 catch(error){process.stderr.write((error instanceof Error&&/^harness-[a-z-]+$/.test(error.message)?error.message:'harness-failed')+'\n');process.exitCode=1;}
}
