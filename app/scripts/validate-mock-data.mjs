import { mockFolder, mockReviewSets, mockSummary } from '../mock/mockReviewData.js';
import fs from 'node:fs';
import path from 'node:path';

const errors = [];
const requiredPhotoFields = [
  'display_id', 'source_path', 'thumb_path', 'thumb_width', 'thumb_height',
  'preview_path', 'preview_width', 'preview_height', 'ui_initial_state',
  'reason_summary_zh', 'weakness_summary_zh'
];

function assert(condition, message) {
  if (!condition) errors.push(message);
}

assert(fs.existsSync(mockFolder), `mock folder missing: ${mockFolder}`);
assert(mockSummary.schema_version === '1.1', 'summary schema_version must be 1.1');
assert(mockSummary.review_set_count === mockReviewSets.length, 'summary review_set_count does not match mockReviewSets length');

for (const set of mockReviewSets) {
  assert(set.schema_version === '1.1', `${set.review_set_id}: schema_version must be 1.1`);
  assert(set.primary_keeper_id, `${set.review_set_id}: missing primary_keeper_id`);
  assert(Array.isArray(set.recommended_keep_ids), `${set.review_set_id}: missing recommended_keep_ids`);
  assert(set.recommended_keep_ids.length === 1, `${set.review_set_id}: recommended_keep_ids should contain primary only`);
  assert(set.recommended_keep_ids[0] === set.primary_keeper_id, `${set.review_set_id}: primary_keeper_id mismatch`);
  assert(Array.isArray(set.alternate_keeper_ids), `${set.review_set_id}: missing alternate_keeper_ids`);
  assert(Array.isArray(set.challenger_queue), `${set.review_set_id}: missing challenger_queue`);
  assert(Array.isArray(set.photos) && set.photos.length === set.photo_count, `${set.review_set_id}: photo_count mismatch`);
  assert(Array.isArray(set.reason_summary_zh), `${set.review_set_id}: reason_summary_zh must be array`);

  const photoIds = new Set(set.photos.map((photo) => photo.display_id));
  assert(photoIds.has(set.primary_keeper_id), `${set.review_set_id}: primary keeper missing from photos`);
  for (const id of set.alternate_keeper_ids) assert(photoIds.has(id), `${set.review_set_id}: alternate ${id} missing from photos`);
  const queueIds = new Set();
  for (const item of set.challenger_queue) {
    assert(photoIds.has(item.photo_id), `${set.review_set_id}: challenger ${item.photo_id} missing from photos`);
    assert(item.photo_id !== set.primary_keeper_id, `${set.review_set_id}: primary should not be in challenger_queue`);
    assert(item.compare_to === set.primary_keeper_id, `${set.review_set_id}: challenger compare_to should be primary`);
    assert(Number.isFinite(item.rank), `${set.review_set_id}: challenger rank missing`);
    queueIds.add(item.photo_id);
  }
  for (const photo of set.photos) {
    if (photo.display_id !== set.primary_keeper_id) assert(queueIds.has(photo.display_id), `${set.review_set_id}: non-primary ${photo.display_id} missing from challenger_queue`);
    for (const field of requiredPhotoFields) assert(photo[field] !== undefined && photo[field] !== null, `${set.review_set_id}/${photo.display_id}: missing ${field}`);
    assert(Array.isArray(photo.reason_summary_zh), `${photo.display_id}: reason_summary_zh must be array`);
    assert(Array.isArray(photo.weakness_summary_zh), `${photo.display_id}: weakness_summary_zh must be array`);
    assert(photo.thumb_width > 0 && photo.thumb_height > 0, `${photo.display_id}: invalid thumb dimensions`);
    assert(photo.preview_width > 0 && photo.preview_height > 0, `${photo.display_id}: invalid preview dimensions`);
    assert(fs.existsSync(path.join(mockFolder, photo.thumb_path)), `${photo.display_id}: thumb file missing`);
    assert(fs.existsSync(path.join(mockFolder, photo.preview_path)), `${photo.display_id}: preview file missing`);
    assert(fs.existsSync(photo.source_path), `${photo.display_id}: source file missing ${photo.source_path}`);
    const raw = photo.compare_metrics?.raw || {};
    assert(Array.isArray(raw.brightness_histogram) && raw.brightness_histogram.length === 64, `${photo.display_id}: brightness_histogram must have 64 bins`);
    assert(raw.rgb_histogram && ['r', 'g', 'b'].every((key) => Array.isArray(raw.rgb_histogram[key]) && raw.rgb_histogram[key].length === 64), `${photo.display_id}: rgb_histogram must have 64 bins per channel`);
  }
}

if (errors.length) {
  console.error(errors.map((error) => `- ${error}`).join('\n'));
  process.exit(1);
}

console.log(`mock review contract ok: ${mockReviewSets.length} sets, ${mockReviewSets.reduce((sum, set) => sum + set.photos.length, 0)} photos`);
