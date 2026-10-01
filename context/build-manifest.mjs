import { readFile, writeFile } from 'node:fs/promises';
import { canonicalJson, dependencyStoreDigest, jsonDigest, parseStrictJson, sha256 } from './harness.mjs';
const recipe=parseStrictJson(await readFile('/opt/cirujano/recipe.json','utf8'));
const manifest={schemaVersion:1,kind:'optimization-image',toolSourceSha:recipe.toolSourceSha,bundleDigest:recipe.bundleDigest,nodeVersion:recipe.nodeVersion,pnpmVersion:recipe.pnpmVersion,lockfileHash:sha256(await readFile('/opt/cirujano/dependency-input/pnpm-lock.yaml')),dependencyStoreHash:await dependencyStoreDigest('/opt/cirujano/store'),harnessHash:sha256(await readFile('/opt/cirujano/harness.mjs')),recipeHash:jsonDigest(recipe)};
await writeFile('/opt/cirujano/image.json',canonicalJson(manifest),{mode:0o600,flag:'wx'});
