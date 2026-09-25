// Run after Vite. Keep license texts with the bundled web application.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const frontend = path.join(root, 'aegis/editor/frontend');
const lock = JSON.parse(fs.readFileSync(path.join(frontend, 'package-lock.json'), 'utf8'));
const output = ['Third-party notices for the AgenticAEGIS web editor.\n'];
for (const [location, info] of Object.entries(lock.packages).sort()) {
  if (!location || info.dev) continue;
  const dir = path.join(frontend, location);
  if (!fs.existsSync(dir)) continue; // Optional platform-specific packages.
  const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
  output.push(`\n${pkg.name} ${pkg.version}\nLicense: ${info.license ?? pkg.license ?? 'See upstream'}\n`);
  const notices = fs.readdirSync(dir).filter(n => /^(licen[sc]e|copying|notice)(\.|$|-)/i.test(n));
  if (!notices.length) {
    // This npm release omits its license file; retain the upstream text locally.
    if (pkg.name === 'html-parse-stringify' && pkg.version === '3.0.1') {
      output.push(fs.readFileSync(path.join(root, 'licenses/html-parse-stringify-LICENSE.txt'), 'utf8'));
      continue;
    }
    throw new Error(`No license text found for bundled runtime dependency: ${pkg.name}`);
  }
  for (const name of notices) {
    const file = path.join(dir, name);
    if (fs.statSync(file).isFile()) output.push(fs.readFileSync(file, 'utf8'));
  }
}
fs.mkdirSync(path.join(frontend, 'dist'), { recursive: true });
fs.writeFileSync(path.join(frontend, 'dist/THIRD_PARTY_NOTICES.txt'), output.join('\n'));
console.log('Wrote bundled frontend dependency notices.');
