import fs from 'node:fs';
import path from 'node:path';

const dist = path.resolve('dist');
const index = path.join(dist, 'index.html');
if (!fs.existsSync(index)) throw new Error('dist/index.html missing; run npm run build first');
const assetsDir = path.join(dist, 'assets');
const assets = fs.readdirSync(assetsDir).filter((name) => name.endsWith('.js') || name.endsWith('.css'));
const corpus = [fs.readFileSync(index, 'utf8'), ...assets.map((name) => fs.readFileSync(path.join(assetsDir, name), 'utf8'))].join('\n');
const sourceCorpus = [
  fs.readFileSync(path.resolve('app/src/App.tsx'), 'utf8'),
  fs.readFileSync(path.resolve('app/src/styles.css'), 'utf8'),
].join('\n');
for (const needle of ['Cullary', '打开 Review', '保留', '对比', '最终确认', '返回主页面']) {
  if (!corpus.includes(needle)) throw new Error(`built UI missing marker: ${needle}`);
}
for (const needle of [
  'compareInspectorOpen',
  'compare-inspector-open',
  'inspector-toggle',
  'hero-action-rail',
  '当前大图操作',
  'deck-inspector',
  '本组进度',
  'back-project-button',
  "draft.mode = 'deck'",
]) {
  if (!sourceCorpus.includes(needle)) throw new Error(`source UI missing review refinement marker: ${needle}`);
}
for (const needle of [
  '.review-shell.compare-mode.compare-inspector-open { grid-template-columns: 200px minmax(0, 1fr) 292px',
  '.review-shell.compare-mode { grid-template-columns: 200px minmax(0, 1fr) 22px',
  '.compare-mode .inspector { position: relative',
  '.compare-mode:not(.compare-inspector-open) .inspector .reason-card',
  '.compact-deck .delete-strip { grid-template-columns: minmax(0, 1fr)',
  '.compact-deck .deck-action-rail { display: none',
]) {
  if (!sourceCorpus.includes(needle)) throw new Error(`source UI missing layout contract: ${needle}`);
}
if (sourceCorpus.includes('滚轮缩放，拖拽平移')) throw new Error('source UI still contains removed interaction hint');
if (sourceCorpus.includes('保持待删除')) throw new Error('source UI still contains removed compare action');
console.log(`built UI smoke ok: ${assets.length} assets`);
