import { copyFile, mkdir, access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const src = path.join(root, 'node_modules', 'chart.js', 'dist', 'chart.umd.js');
const destDir = path.join(root, 'out', 'media');
const dest = path.join(destDir, 'chart.umd.js');

try {
  await access(src);
} catch {
  console.error(`[copy-assets] missing ${src}. Did you run "npm install"?`);
  process.exit(1);
}

await mkdir(destDir, { recursive: true });
await copyFile(src, dest);
console.log(`[copy-assets] ${path.relative(root, src)} -> ${path.relative(root, dest)}`);
