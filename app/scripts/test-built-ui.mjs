import fs from 'node:fs';
import path from 'node:path';

const dist = path.resolve('dist');
const index = path.join(dist, 'index.html');
if (!fs.existsSync(index)) throw new Error('dist/index.html missing; run npm run build first');
const assetsDir = path.join(dist, 'assets');
const assets = fs.readdirSync(assetsDir).filter((name) => name.endsWith('.js') || name.endsWith('.css'));
const corpus = [fs.readFileSync(index, 'utf8'), ...assets.map((name) => fs.readFileSync(path.join(assetsDir, name), 'utf8'))].join('\n');
for (const needle of ['Cullary', '打开 Review', '保留', '进入对比', '最终确认']) {
  if (!corpus.includes(needle)) throw new Error(`built UI missing marker: ${needle}`);
}
console.log(`built UI smoke ok: ${assets.length} assets`);
