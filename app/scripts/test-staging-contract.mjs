import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { mockFolder, mockReviewSets } from '../mock/mockReviewData.js';

const keepIds = new Set(mockReviewSets.flatMap((set) => set.photos.filter((photo) => photo.ui_initial_state === 'recommended_keep').map((photo) => photo.display_id)));
const targetIds = mockReviewSets.flatMap((set) => set.photos.map((photo) => photo.display_id)).filter((id) => !keepIds.has(id));
const photos = new Map(mockReviewSets.flatMap((set) => set.photos.map((photo) => [photo.display_id, photo])));
const operations = [];
const issues = [];

for (const displayId of targetIds) {
  const photo = photos.get(displayId);
  if (!photo?.source_path) {
    issues.push({ display_id: displayId, issue: 'missing_source_path' });
    continue;
  }
  assert.ok(fs.existsSync(photo.source_path), `${displayId} source exists`);
  const rel = path.relative(mockFolder, photo.source_path);
  operations.push({ display_id: displayId, kind: 'source', source: photo.source_path, destination: path.join(mockFolder, '.to_delete', rel) });
  const seenSidecars = new Set();
  for (const ext of ['xmp', 'XMP']) {
    const sidecar = photo.source_path.replace(/\.[^.]+$/, `.${ext}`);
    if (fs.existsSync(sidecar)) {
      const real = fs.realpathSync(sidecar).toLowerCase();
      if (seenSidecars.has(real)) continue;
      seenSidecars.add(real);
      operations.push({ display_id: displayId, kind: 'sidecar', source: sidecar, destination: path.join(mockFolder, '.to_delete', path.relative(mockFolder, sidecar)) });
    }
  }
}

assert.equal(issues.length, 0);
assert.equal(operations.filter((op) => op.kind === 'source').length, 11);
assert.equal(operations.filter((op) => op.kind === 'sidecar').length, 1);
assert.ok(operations.every((op) => op.destination.includes(`${path.sep}.to_delete${path.sep}`)), 'destinations use .to_delete');
console.log(`staging contract ok: ${operations.length} planned operations`);
