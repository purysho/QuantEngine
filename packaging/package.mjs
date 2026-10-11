import { packager } from '@electron/packager';
import { readFile, writeFile, cp, access, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
await access(path.join(root,'dist/main.cjs'));
await access(path.join(root,'runtime/quant-python/python.exe'));
const pkg=JSON.parse(await readFile(path.join(root,'package.json'),'utf8'));
// Replace only this generated output; runtime and research data live elsewhere.
await rm(path.join(root,'release','Quant Engine-win32-x64'),{recursive:true,force:true});
const packages=await packager({
  dir:root, name:"Quant Engine", executableName:"QuantEngine",
  platform:'win32', arch:'x64', electronVersion:pkg.devDependencies.electron,
  appVersion:pkg.version, buildVersion:pkg.version,
  appCopyright:'Copyright 2026. Application code: UNLICENSED. Third-party notices included.',
  icon:path.join(root,'assets/app.ico'), out:path.join(root,'release'),
  overwrite:true, asar:false, prune:true,
  // Optional offline/proxied builds: a folder holding a checksum-verified electron-v<version>-win32-x64.zip.
  ...(process.env.ELECTRON_ZIP_DIR?{electronZipDir:path.resolve(process.env.ELECTRON_ZIP_DIR)}:{}),
  extraResource:[path.join(root,'runtime/quant-python')],
  ignore:[/^\/runtime(?:\/|$)/,/^\/release(?:\/|$)/,/^\/tests(?:\/|$)/,
    /^\/packaging(?:\/|$)/,/^\/desktop(?:\/|$)/,/^\/docs\/superpowers(?:\/|$)/,
    /^\/docs\/PROGRESS\.md$/,/^\/\.git(?:\/|$)/,/^\/\.github(?:\/|$)/,/^\/\.cache(?:\/|$)/,/^\/\.gitignore$/,
    /^\/tsconfig\.json$/,/^\/package-lock\.json$/,/__pycache__/,/\.pyc$/],
  win32metadata:{CompanyName:"Quant Engine",FileDescription:"Quant Engine",ProductName:"Quant Engine",OriginalFilename:"QuantEngine.exe"}
});
for(const folder of packages){
  await cp(path.join(root,'docs/USER_GUIDE.md'),path.join(folder,'START_HERE.md'));
  const metadata={product:"Quant Engine",version:pkg.version,platform:'Windows x64',
    executable:"QuantEngine.exe",runtime:"quant-python",
    builtAt:new Date().toISOString(),deviceValidation:'Target Windows laptop validation pending'};
  await writeFile(path.join(folder,'BUILD_INFO.json'),JSON.stringify(metadata,null,2)+'\n');
  console.log(folder);
}

