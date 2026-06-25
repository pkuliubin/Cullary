export function createReviewState({ folder, summary = null, reviewSets = [] }) {
  return {
    screen: 'start',
    folder,
    summary,
    reviewSets,
    activeSetIndex: 0,
    activePhotoId: null,
    activeKeeperId: null,
    activeChallengerId: null,
    mode: 'deck',
    decisions: new Map(),
    completedSets: new Set(),
    pipelineEvents: [],
    pipelineStatus: 'idle',
    pipelineTaskId: null,
    stagePlan: null,
    stageResult: null,
    lastAction: null,
    compare: {
      linked: true,
      scale: 1,
      x: 0,
      y: 0,
      left: { scale: 1, x: 0, y: 0 },
      right: { scale: 1, x: 0, y: 0 },
    },
  };
}

export function applyPersistedDecisions(state, decisions = []) {
  for (const event of decisions) {
    if (!event?.display_id || !event?.user_state) continue;
    state.decisions.set(event.display_id, event.user_state);
  }
  ensureActivePointers(state);
}

export function applyReviewProgress(state, progress = {}) {
  state.completedSets = new Set(progress.completed_review_set_ids || []);
}

export function activeSet(state) {
  return state.reviewSets[state.activeSetIndex];
}

export function photoById(set, id) {
  return set?.photos?.find((photo) => photo.display_id === id);
}

export function photoInitialState(set, photo) {
  if (!photo) return 'user_undecided';
  if (photo.ui_initial_state === 'recommended_keep') return 'user_keep';
  if (photo.ui_initial_state === 'recommended_alternate') return 'user_challenger';
  if (photo.ui_initial_state === 'not_prioritized') return 'user_challenger';
  return photo.ui_initial_state || 'user_undecided';
}

export function decisionFor(state, photo) {
  if (!photo) return 'user_undecided';
  return state.decisions.get(photo.display_id) || photoInitialState(activeSet(state), photo);
}

export function isAlternate(set, photo) {
  return Boolean(photo && (set?.alternate_keeper_ids || []).includes(photo.display_id));
}

export function primaryKeeper(state) {
  const set = activeSet(state);
  return photoById(set, set?.primary_keeper_id || set?.recommended_keep_ids?.[0]);
}

export function challengerQueueIds(set) {
  const ids = (set?.challenger_queue || []).map((item) => item.photo_id);
  const seen = new Set(ids);
  for (const photo of set?.photos || []) {
    if (photo.display_id !== set?.primary_keeper_id && !seen.has(photo.display_id)) ids.push(photo.display_id);
  }
  return ids;
}

export function challengerMeta(set, photoId) {
  return (set?.challenger_queue || []).find((item) => item.photo_id === photoId) || null;
}


export function allReviewPhotos(state) {
  return (state.reviewSets || []).flatMap((set) => set.photos || []);
}

export function deletePhotos(state) {
  const set = activeSet(state);
  if (!set) return [];
  return (set.photos || []).filter((photo) => decisionFor(state, photo) !== 'user_keep');
}

export function allDeletePhotos(state) {
  return (state.reviewSets || []).flatMap((set, index) => {
    const localState = { ...state, activeSetIndex: index };
    return (set.photos || []).filter((photo) => decisionFor(localState, photo) !== 'user_keep');
  });
}

export function keeperPhotos(state) {
  const set = activeSet(state);
  if (!set) return [];
  return (set.photos || [])
    .filter((photo) => decisionFor(state, photo) === 'user_keep')
    .sort((a, b) => {
      const primary = set.primary_keeper_id || set.recommended_keep_ids?.[0];
      if (a.display_id === primary) return -1;
      if (b.display_id === primary) return 1;
      return (a.rank || 0) - (b.rank || 0);
    });
}

export function moveAsidePhotos(state) {
  return [];
}

export function challengerPhotos(state) {
  const set = activeSet(state);
  if (!set) return [];
  const byId = new Map((set.photos || []).map((photo) => [photo.display_id, photo]));
  const ordered = [];
  const seen = new Set();
  for (const id of challengerQueueIds(set)) {
    const photo = byId.get(id);
    if (!photo || seen.has(id)) continue;
    const stateValue = decisionFor(state, photo);
    if (stateValue !== 'user_keep') {
      ordered.push(photo);
      seen.add(id);
    }
  }
  for (const photo of set.photos || []) {
    if (seen.has(photo.display_id)) continue;
    const stateValue = decisionFor(state, photo);
    if (stateValue !== 'user_keep') ordered.push(photo);
  }
  return ordered;
}

export function activePhoto(state) {
  const set = activeSet(state);
  return photoById(set, state.activePhotoId) || activeKeeper(state) || challengerPhotos(state)[0] || set?.photos?.[0];
}

export function activeKeeper(state) {
  const set = activeSet(state);
  return photoById(set, state.activeKeeperId) || keeperPhotos(state)[0] || primaryKeeper(state);
}

export function activeChallenger(state) {
  const set = activeSet(state);
  const current = photoById(set, state.activeChallengerId);
  if (current && challengerPhotos(state).some((photo) => photo.display_id === current.display_id)) return current;
  return challengerPhotos(state)[0];
}

export function counts(state) {
  return {
    keepers: keeperPhotos(state).length,
    challengers: challengerPhotos(state).length,
    moveAside: moveAsidePhotos(state).length,
  };
}

export function selectSet(state, index) {
  state.activeSetIndex = clamp(index, 0, Math.max(state.reviewSets.length - 1, 0));
  state.activePhotoId = null;
  state.activeKeeperId = null;
  state.activeChallengerId = null;
  state.mode = 'deck';
  resetZoom(state);
}

export function selectKeeper(state, photoId) {
  state.activeKeeperId = photoId;
  state.activePhotoId = photoId;
  resetZoom(state);
}

export function selectChallenger(state, indexOrId) {
  const challengers = challengerPhotos(state);
  const photo = typeof indexOrId === 'number'
    ? challengers[clamp(indexOrId, 0, Math.max(challengers.length - 1, 0))]
    : challengers.find((item) => item.display_id === indexOrId);
  if (!photo) return;
  state.activeChallengerId = photo.display_id;
  state.activePhotoId = photo.display_id;
  resetZoom(state);
}

export function selectMoveAside(state, photoId) {
  state.activePhotoId = photoId;
  resetZoom(state);
}

export function nextChallenger(state) {
  const challengers = challengerPhotos(state);
  if (!challengers.length) {
    state.activeChallengerId = null;
    return;
  }
  const currentIndex = Math.max(0, challengers.findIndex((photo) => photo.display_id === activeChallenger(state)?.display_id));
  state.activeChallengerId = challengers[(currentIndex + 1) % challengers.length].display_id;
  if (state.mode !== 'compare') resetZoom(state);
}

export function previousChallenger(state) {
  const challengers = challengerPhotos(state);
  if (!challengers.length) {
    state.activeChallengerId = null;
    return;
  }
  const currentIndex = Math.max(0, challengers.findIndex((photo) => photo.display_id === activeChallenger(state)?.display_id));
  state.activeChallengerId = challengers[(currentIndex - 1 + challengers.length) % challengers.length].display_id;
  if (state.mode !== 'compare') resetZoom(state);
}

export function setDecisionState(state, photo, userState) {
  if (!photo) return 'user_undecided';
  const previous = decisionFor(state, photo);
  state.decisions.set(photo.display_id, userState);
  if (userState === 'user_keep') {
    state.activeKeeperId = photo.display_id;
    state.activePhotoId = photo.display_id;
    if (state.activeChallengerId === photo.display_id) state.activeChallengerId = null;
  }
  if (userState === 'user_challenger') {
    if (state.activeKeeperId === photo.display_id) state.activeKeeperId = null;
    state.activeChallengerId = photo.display_id;
    state.activePhotoId = photo.display_id;
  }
  if (userState === 'user_marked_move_aside') {
    if (state.activeKeeperId === photo.display_id) state.activeKeeperId = null;
    if (state.activeChallengerId === photo.display_id) state.activeChallengerId = null;
    state.activePhotoId = photo.display_id;
  }
  ensureActivePointers(state);
  return previous;
}

export function replaceWithChallenger(state) {
  const keeper = activeKeeper(state);
  const challenger = activeChallenger(state);
  if (!keeper || !challenger) return null;
  const previousKeeper = setDecisionState(state, keeper, 'user_challenger');
  const previousChallenger = setDecisionState(state, challenger, 'user_keep');
  state.activeKeeperId = challenger.display_id;
  state.activePhotoId = challenger.display_id;
  state.activeChallengerId = null;
  ensureActivePointers(state);
  resetZoom(state);
  return { keeper, challenger, previousKeeper, previousChallenger };
}

export function keepBoth(state) {
  const keeper = activeKeeper(state);
  const challenger = activeChallenger(state);
  if (!keeper || !challenger) return null;
  const previousKeeper = setDecisionState(state, keeper, 'user_keep');
  const previousChallenger = setDecisionState(state, challenger, 'user_keep');
  state.activeKeeperId = challenger.display_id;
  state.activePhotoId = challenger.display_id;
  state.activeChallengerId = null;
  ensureActivePointers(state);
  resetZoom(state);
  return { keeper, challenger, previousKeeper, previousChallenger };
}

export function moveAsideActiveChallenger(state) {
  const challenger = activeChallenger(state);
  if (!challenger) return null;
  const previous = setDecisionState(state, challenger, 'user_marked_move_aside');
  state.activeChallengerId = null;
  ensureActivePointers(state);
  resetZoom(state);
  return { challenger, previous };
}

export function ensureActivePointers(state) {
  const keeper = activeKeeper(state);
  const challenger = activeChallenger(state);
  if (!state.activeKeeperId && keeper) state.activeKeeperId = keeper.display_id;
  if (!state.activeChallengerId && challenger) state.activeChallengerId = challenger.display_id;
}

export function updateZoom(state, side, updater) {
  if (state.compare.linked) {
    Object.assign(state.compare, updater(state.compare));
  } else {
    state.compare[side] = updater(state.compare[side]);
  }
}

export function resetZoom(state) {
  state.compare.scale = 1;
  state.compare.x = 0;
  state.compare.y = 0;
  state.compare.left = { scale: 1, x: 0, y: 0 };
  state.compare.right = { scale: 1, x: 0, y: 0 };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, Number(value) || 0));
}
