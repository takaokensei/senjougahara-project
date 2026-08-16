import { execSync } from 'child_process';
import { resolve, dirname } from 'path';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(resolve(__dirname, '../package.json'), 'utf8'));
const v = pkg.version;
const sevenZip = resolve(__dirname, '../node_modules/7zip-bin/win/x64/7za.exe');

// インストーラーを zip に固める（BOOTH は .exe 直接不可）
const installerExe = resolve(__dirname, `../release/Desktop Mascot Setup ${v}.exe`);
const installerZip = resolve(__dirname, `../release/Desktop-Mascot-Setup-${v}-win-x64.zip`);
console.log(`Zipping installer for BOOTH...`);
execSync(`"${sevenZip}" a -tzip "${installerZip}" "${installerExe}"`, { stdio: 'inherit' });
console.log(`Done: release/Desktop-Mascot-Setup-${v}-win-x64.zip`);
