import assert from 'node:assert/strict';
import { mockFolder, mockReviewSets, mockSummary } from '../mock/mockReviewData.js';
import {
  activeChallenger,
  activeKeeper,
  activePhoto,
  activeSet,
  challengerPhotos,
  counts,
  createReviewState,
  decisionFor,
  keeperPhotos,
  keepBoth,
  moveAsidePhotos,
  nextChallenger,
  previousChallenger,
  replaceWithChallenger,
  resetZoom,
  selectChallenger,
  selectKeeper,
  selectSet,
  setDecisionState,
  updateZoom,
} from '../src/reviewState.js';

const state = createReviewState({ folder: mockFolder, summary: mockSummary, reviewSets: mockReviewSets });

assert.equal(activeSet(state).review_set_id, 'set_demo_001');
assert.equal(activeSet(state).schema_version, '1.1');
assert.equal(activeKeeper(state).display_id, 'DEMO_0001_JPG');
assert.equal(activeChallenger(state).display_id, 'DEMO_0004_JPG');
assert.deepEqual(counts(state), { keepers: 1, challengers: 11, moveAside: 0 });
assert.equal(keeperPhotos(state).map((photo) => photo.display_id).join(','), 'DEMO_0001_JPG');
assert.equal(challengerPhotos(state)[0].display_id, 'DEMO_0004_JPG');

selectChallenger(state, 'DEMO_0002_JPG');
assert.equal(activePhoto(state).display_id, 'DEMO_0002_JPG');
assert.equal(activeChallenger(state).display_id, 'DEMO_0002_JPG');
nextChallenger(state);
assert.equal(activeChallenger(state).display_id, 'DEMO_0003_JPG');
previousChallenger(state);
assert.equal(activeChallenger(state).display_id, 'DEMO_0002_JPG');

const previous = setDecisionState(state, activeChallenger(state), 'user_keep');
assert.equal(previous, 'user_undecided');
assert.equal(decisionFor(state, activeKeeper(state)), 'user_keep');
assert.equal(keeperPhotos(state).some((photo) => photo.display_id === 'DEMO_0002_JPG'), true);
assert.equal(challengerPhotos(state).some((photo) => photo.display_id === 'DEMO_0002_JPG'), false);

selectKeeper(state, 'DEMO_0001_JPG');
selectChallenger(state, 'DEMO_0003_JPG');
const replaceResult = replaceWithChallenger(state);
assert.equal(replaceResult.keeper.display_id, 'DEMO_0001_JPG');
assert.equal(replaceResult.challenger.display_id, 'DEMO_0003_JPG');
assert.equal(decisionFor(state, replaceResult.keeper), 'user_challenger');
assert.equal(decisionFor(state, replaceResult.challenger), 'user_keep');
assert.equal(activeKeeper(state).display_id, 'DEMO_0003_JPG');
assert.equal(challengerPhotos(state).some((photo) => photo.display_id === 'DEMO_0003_JPG'), false);
assert.equal(challengerPhotos(state).some((photo) => photo.display_id === 'DEMO_0001_JPG'), true);

selectChallenger(state, 'DEMO_0005_JPG');
const both = keepBoth(state);
assert.equal(decisionFor(state, both.keeper), 'user_keep');
assert.equal(decisionFor(state, both.challenger), 'user_keep');
assert.equal(challengerPhotos(state).some((photo) => photo.display_id === 'DEMO_0005_JPG'), false);

selectChallenger(state, 'DEMO_0006_JPG');
assert.equal(decisionFor(state, activeChallenger(state)), 'user_undecided');
assert.equal(challengerPhotos(state).some((photo) => photo.display_id === 'DEMO_0006_JPG'), true);
assert.equal(moveAsidePhotos(state).length, 0);

state.compare.linked = true;
updateZoom(state, 'left', (view) => ({ ...view, scale: 2, x: 12, y: -4 }));
assert.equal(state.compare.scale, 2);
assert.equal(state.compare.x, 12);
state.compare.linked = false;
updateZoom(state, 'right', (view) => ({ ...view, scale: 3, x: 8, y: 9 }));
assert.equal(state.compare.right.scale, 3);
assert.equal(state.compare.left.scale, 1);
resetZoom(state);
assert.equal(state.compare.scale, 1);
assert.equal(state.compare.right.scale, 1);

selectSet(state, 0);
assert.equal(state.mode, 'deck');
assert.equal(decisionFor(state, activeKeeper(state)), 'user_keep');

console.log('review state flow ok');
