import React, { useEffect, useRef, useState } from 'react';
import { mockFolder } from '../mock/mockReviewData.js';
import { repository, resolveAssetPath } from './repository.js';
import {
  activeChallenger,
  activeKeeper,
  activePhoto,
  activeSet,
  allDeletePhotos,
  allReviewPhotos,
  challengerMeta,
  challengerPhotos,
  deletePhotos,
  counts,
  createReviewState,
  decisionFor,
  isAlternate,
  keeperPhotos,
  keepBoth,
  moveAsidePhotos,
  nextChallenger,
  photoById,
  previousChallenger,
  replaceWithChallenger,
  resetZoom,
  resetDeckZoom,
  selectChallenger,
  selectKeeper,
  selectSet,
  setDecisionState,
  togglePhotoSelected,
  selectPhotoRange,
  clearPhotoSelection,
  updateDeckZoom,
  updateZoom,
  applyPersistedDecisions,
  applyReviewProgress,
} from './reviewState.js';

function cloneState(state: any) {
  return { ...state, decisions: new Map(state.decisions), completedSets: new Set(state.completedSets || []), selectedPhotoIds: new Set(state.selectedPhotoIds || []), compare: { ...state.compare, left: { ...state.compare.left }, right: { ...state.compare.right } }, deckZoom: { ...(state.deckZoom || { scale: 1, x: 0, y: 0 }) } };
}

function decisionLabel(value: string) {
  if (value === 'user_keep') return '保留';
  if (value === 'user_challenger') return '待删除';
  if (value === 'user_marked_move_aside') return '待删除';
  if (value === 'recommended_alternate') return '备选';
  if (value === 'recommended_keep') return '推荐';
  if (value === 'not_prioritized') return '未优先';
  return '待确认';
}

function scoreText(photo: any) {
  const value = photo?.score?.overall;
  return Number.isFinite(value) ? Math.round(value * 100) : '—';
}

function baseScoreText(photo: any) {
  const value = photo?.score?.base_overall;
  return Number.isFinite(value) ? Math.round(value * 100) : '—';
}

function formatDelta(value: any) {
  return Number.isFinite(value) ? `${value > 0 ? '+' : ''}${Math.round(value * 100)}` : null;
}

function formatBytes(bytes: any) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

const scoreDimensionLabels: Record<string, string> = {
  technical_quality: '技术质量',
  iqa: 'IQA 质量',
  composition: '构图',
  face_quality: '人脸质量',
};

const scoreDimensionWeights: Record<string, number> = {
  technical_quality: 0.35,
  face_quality: 0.2,
  iqa: 0.25,
  composition: 0.2,
};

const compareMetricDefs = [
  { key: 'sharpness', label: '整体清晰度', group: '技术', weight: 0.35 * 0.35 },
  { key: 'exposure_clip', label: '曝光裁切', group: '技术', weight: 0.35 * 0.2 },
  { key: 'brightness', label: '亮度居中', group: '技术', weight: 0.35 * 0.1 },
  { key: 'contrast', label: '对比度', group: '技术', weight: 0.35 * 0.15 },
  { key: 'dynamic_range', label: '动态范围', group: '技术', weight: 0.35 * 0.1 },
  { key: 'color_cast', label: '色偏控制', group: '技术', weight: 0.35 * 0.1 },
  { key: 'piqe', label: 'PIQE 质量', group: 'IQA', weight: 0.25 * 0.7 },
  { key: 'aesthetic', label: '美学分', group: 'IQA', weight: 0.25 * 0.3 },
  { key: 'face_sharpness', label: '人脸清晰度', group: '人脸', weight: 0.2 * 0.4 },
  { key: 'face_size', label: '人脸面积', group: '人脸', weight: 0.2 * 0.25 },
  { key: 'face_alignment', label: '人脸角度', group: '人脸', weight: 0.2 * 0.2 },
  { key: 'center_sharpness', label: '中心清晰度', group: '构图', weight: 0.2 * 0.45 },
  { key: 'center_brightness', label: '中心亮度', group: '构图', weight: 0.2 * 0.35 },
  { key: 'aspect', label: '画幅比例', group: '构图', weight: 0.2 * 0.2 },
];

function scoreDimensions(left: any, right: any) {
  const leftScore = left?.score || {};
  const rightScore = right?.score || {};
  return Object.entries(scoreDimensionLabels)
    .map(([key, label]) => {
      const leftValue = Number(leftScore[key]);
      const rightValue = Number(rightScore[key]);
      if (!Number.isFinite(leftValue) || !Number.isFinite(rightValue)) return null;
      return { key, label, left: Math.round(leftValue * 100), right: Math.round(rightValue * 100), diff: Math.round((rightValue - leftValue) * 100) };
    })
    .filter(Boolean)
    .sort((a: any, b: any) => Math.abs(b.diff * (scoreDimensionWeights[b.key] || 0.1)) - Math.abs(a.diff * (scoreDimensionWeights[a.key] || 0.1)));
}

function compareMetricRows(left: any, right: any) {
  const leftValues = left?.compare_metrics?.values || {};
  const rightValues = right?.compare_metrics?.values || {};
  return compareMetricDefs
    .map((def) => {
      const leftValue = Number(leftValues[def.key]);
      const rightValue = Number(rightValues[def.key]);
      if (!Number.isFinite(leftValue) || !Number.isFinite(rightValue)) return null;
      const diff = rightValue - leftValue;
      return { ...def, left: Math.round(leftValue * 100), right: Math.round(rightValue * 100), diff: Math.round(diff * 100), impact: diff * def.weight };
    })
    .filter(Boolean)
    .sort((a: any, b: any) => Math.abs(b.impact) - Math.abs(a.impact));
}

function brightnessHistogram(photo: any) {
  const hist = photo?.compare_metrics?.raw?.brightness_histogram || photo?.compare_metrics?.raw?.brightness_histogram_16;
  if (Array.isArray(hist) && hist.length) return hist.map((v: any) => Math.max(0, Number(v) || 0));
  const raw = photo?.compare_metrics?.raw || {};
  const p05 = Number(raw.brightness_p05); const p50 = Number(raw.brightness_p50); const p95 = Number(raw.brightness_p95);
  if (![p05, p50, p95].every(Number.isFinite)) return [];
  const bins = Array.from({ length: 64 }, (_, idx) => {
    const center = (idx + 0.5) * 4;
    const width = Math.max(18, (p95 - p05) / 2.4);
    return Math.exp(-0.5 * Math.pow((center - p50) / width, 2));
  });
  const total = bins.reduce((sum, value) => sum + value, 0) || 1;
  return bins.map((value) => value / total);
}

function rgbHistogram(photo: any) {
  const hist = photo?.compare_metrics?.raw?.rgb_histogram;
  if (!hist || !Array.isArray(hist.r) || !Array.isArray(hist.g) || !Array.isArray(hist.b)) return null;
  return {
    r: hist.r.map((v: any) => Math.max(0, Number(v) || 0)),
    g: hist.g.map((v: any) => Math.max(0, Number(v) || 0)),
    b: hist.b.map((v: any) => Math.max(0, Number(v) || 0)),
  };
}

function clipText(photo: any) {
  const raw = photo?.compare_metrics?.raw || {};
  const shadow = Number(raw.shadow_clip_ratio);
  const highlight = Number(raw.highlight_clip_ratio);
  if (!Number.isFinite(shadow) || !Number.isFinite(highlight)) return null;
  return `阴影 ${(shadow * 100).toFixed(1)}% · 高光 ${(highlight * 100).toFixed(1)}%`;
}

function photoBytes(photo: any) {
  return Number(photo?.source_size_bytes) || Number(photo?.file_size_bytes) || Number(photo?.source_bytes) || 0;
}

function sortedReviewSets(reviewSets: any[]) {
  return [...reviewSets].sort((a, b) => (b.photo_count || 0) - (a.photo_count || 0));
}

function sourceBytesForPhotos(photos: any[]) {
  return photos.reduce((total, photo) => total + photoBytes(photo), 0);
}

function photoIdList(photos: any[]) {
  return new Set(photos.map((photo) => photo.display_id));
}

function bytesForPlanPhotos(plan: any, photos: any[]) {
  if (!plan?.operations) return sourceBytesForPhotos(photos);
  const ids = photoIdList(photos);
  return plan.operations.filter((op: any) => ids.has(op.display_id) && op.kind === 'source').reduce((sum: number, op: any) => sum + (Number(op.bytes) || 0), 0);
}

function isSetCompleted(state: any, set: any) {
  return Boolean(state.completedSets?.has(set?.review_set_id));
}

export default function App() {
  const [state, setState] = useState<any>(() => createReviewState({ folder: mockFolder }));
  const set = activeSet(state);

  const mutate = (fn: (draft: any) => void) => setState((prev: any) => {
    const draft = cloneState(prev);
    fn(draft);
    return draft;
  });

  const loadMockReview = async () => {
    const folder = state.folder;
    const [summary, reviewSets, decisions, progress] = await Promise.all([
      repository.loadReviewSummary(folder),
      repository.loadReviewSets(folder),
      repository.loadDecisions(folder),
      repository.loadReviewProgress(folder),
    ]);
    const next = createReviewState({ folder, summary, reviewSets: sortedReviewSets(reviewSets) });
    next.screen = 'review';
    applyPersistedDecisions(next, decisions);
    applyReviewProgress(next, progress);
    setState(next);
  };
  const returnToStart = () => {
    setState((prev: any) => ({ ...createReviewState({ folder: prev.folder }), screen: 'start' }));
  };

  const appendDecision = (draft: any, photo: any, userState: string, previous: string, source = 'manual') => {
    return repository.appendDecision(draft.folder, {
      review_set_id: activeSet(draft).review_set_id,
      display_id: photo.display_id,
      previous_user_state: previous,
      user_state: userState,
      source,
    });
  };

  const saveDecision = (photo: any, userState: string, source = 'manual') => {
    let folder = state.folder;
    mutate((draft) => {
      folder = draft.folder;
      const previous = setDecisionState(draft, photo, userState);
      appendDecision(draft, photo, userState, previous, source);
      draft.stagePlan = null;
      draft.lastAction = `${photo.display_id}: ${decisionLabel(userState)}`;
    });
  };

  const saveDecisions = (photos: any[], userState: string, source = 'batch') => {
    const list = (photos || []).filter(Boolean);
    if (!list.length) return;
    mutate((draft) => {
      for (const photo of list) {
        const previous = setDecisionState(draft, photo, userState);
        appendDecision(draft, photo, userState, previous, source);
      }
      clearPhotoSelection(draft);
      draft.stagePlan = null;
      draft.lastAction = `${list.length} 张已标记为${decisionLabel(userState)}`;
    });
  };

  useEffect(() => {
    let cleanup: any = null;
    repository.listenPipelineEvents((event: any) => {
      setState((prev: any) => {
        const draft = cloneState(prev);
        draft.pipelineEvents = [...draft.pipelineEvents.slice(-20), event];
        if (event.taskId && event.taskId !== draft.pipelineTaskId) return draft;
        if (event.type === 'completed') draft.pipelineStatus = 'completed';
        else if (event.type === 'failed') draft.pipelineStatus = 'failed';
        else if (event.type === 'cancelled') draft.pipelineStatus = 'cancelled';
        else if (event.type === 'progress') draft.pipelineStatus = 'running';
        return draft;
      });
    }).then((unlisten: any) => { cleanup = unlisten; });
    return () => { if (cleanup) cleanup(); };
  }, []);

  useEffect(() => {
    if (!state.lastAction) return;
    const timer = window.setTimeout(() => setState((prev: any) => ({ ...prev, lastAction: null })), 1600);
    return () => window.clearTimeout(timer);
  }, [state.lastAction]);

  useEffect(() => {
    if (state.lastAction) setState((prev: any) => ({ ...prev, lastAction: null }));
  }, [state.activeSetIndex]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && state.mode === 'compare') mutate((draft) => { draft.mode = 'deck'; });
      if (state.mode === 'compare' && event.key === 'ArrowRight') mutate(nextChallenger);
      if (state.mode === 'compare' && event.key === 'ArrowLeft') mutate(previousChallenger);
      if (event.key.toLowerCase() === 'c' && state.screen === 'review') mutate((draft) => { draft.mode = 'compare'; });
      if (event.key.toLowerCase() === 'l') mutate((draft) => { draft.compare.linked = !draft.compare.linked; });
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [state.mode, state.screen]);

  if (state.screen === 'processing') return <ProcessingScreen state={state} loadMockReview={loadMockReview} mutate={mutate} />;
  if (state.screen === 'review' && set) return <ReviewScreen state={state} mutate={mutate} saveDecision={saveDecision} saveDecisions={saveDecisions} appendDecision={appendDecision} returnToStart={returnToStart} />;
  if (state.screen === 'staging') return <StagingScreen state={state} mutate={mutate} returnToStart={returnToStart} />;
  return <StartScreen state={state} mutate={mutate} loadMockReview={loadMockReview} />;
}

function StartScreen({ state, mutate, loadMockReview }: any) {
  return <main className="start-screen">
    <section className="start-copy"><h1>Cullary</h1><p>One burst, one best.</p></section>
    <section className="start-panel">
      <label>文件夹</label>
      <div className="folder-row"><code>{state.folder}</code><button onClick={async () => { const folder = await repository.chooseFolder(); if (folder) mutate((draft: any) => { draft.folder = folder; }); }}>选择</button></div>
      <button className="primary wide" onClick={loadMockReview}>打开 Review</button>
      <button className="secondary wide" onClick={async () => { mutate((draft: any) => { draft.screen = 'processing'; draft.pipelineStatus = 'running'; draft.pipelineEvents = [{ type: 'progress', stage: 'start', done: 0, total: 1, message: 'Starting pipeline' }]; }); const task = await repository.startPipeline(state.folder); mutate((draft: any) => { draft.pipelineTaskId = task?.taskId || null; }); }}>开始分析</button>
    </section>
  </main>;
}

function ProcessingScreen({ state, loadMockReview, mutate }: any) {
  const stageGroups = [
    { key: 'scan', label: '查找照片', stages: [{ key: 'scan', label: '扫描文件' }] },
    { key: 'prepare', label: '准备预览', stages: [{ key: 'metadata', label: '读取拍摄信息' }, { key: 'preview', label: '生成预览' }, { key: 'thumb', label: '生成缩略图' }, { key: 'hash', label: '计算指纹' }] },
    { key: 'analyze', label: '分析画面', stages: [{ key: 'face', label: '检测人脸' }, { key: 'person_mask', label: '识别主体' }, { key: 'image_metrics', label: '画面指标' }, { key: 'embedding', label: '相似画面' }, { key: 'iqa', label: '画质评分' }] },
    { key: 'review', label: '整理 Review', stages: [{ key: 'review_load', label: '读取结果' }, { key: 'review_sets', label: '生成分组' }] },
  ];
  const progress = buildPipelineProgress(state.pipelineEvents, stageGroups, state.pipelineStatus);
  const statusLabel = state.pipelineStatus === 'failed' ? '分析失败' : state.pipelineStatus === 'running' ? '分析中' : state.pipelineStatus === 'completed' ? '已完成' : state.pipelineStatus;
  const currentLabel = progress.currentSubstage?.label || progress.currentGroup?.label || '准备中';
  return <main className="processing-screen">
    <header className="processing-side"><button onClick={() => mutate((draft: any) => { draft.screen = 'start'; })}>返回</button><h2>处理中</h2></header>
    <section className="progress-panel">
      <p className="eyebrow">正在分析</p>
      <h3>{state.folder}</h3>
      <div className={`pipeline-status ${state.pipelineStatus}`}><span>{statusLabel}</span><strong>{currentLabel}</strong>{progress.latest?.total ? <em>{progress.latest.done || 0}/{progress.latest.total}</em> : <em>{progress.overallPercent}%</em>}</div>
      <div className="pipeline-track" aria-label="分析进度">{stageGroups.map((group, index) => {
        const completed = group.stages.filter((sub: any) => (progress.stagePercents[sub.key] || 0) >= 100).length;
        const total = group.stages.length;
        const percent = Math.round((completed / total) * 100);
        const isDone = completed === total;
        const isActive = progress.currentGroup?.key === group.key && state.pipelineStatus !== 'completed';
        return <div className={`pipeline-step ${isDone ? 'done' : ''} ${isActive ? 'active' : ''}`} key={group.key}>
          <div className="step-ring" style={{ background: `conic-gradient(var(--accent) ${percent * 3.6}deg, #151914 0deg)` }}><span>{completed}/{total}</span></div>
          <strong>{group.label}</strong>
          <small>{isDone ? '完成' : isActive ? `子步骤 ${completed}/${total}` : '等待中'}</small>
        </div>;
      })}</div>
      {progress.currentGroup && <div className="current-substages"><p className="eyebrow">当前步骤</p>{progress.currentGroup.stages.map((sub: any) => { const percent = progress.stagePercents[sub.key] || 0; return <span key={sub.key} className={percent >= 100 ? 'done' : progress.latest?.stage === sub.key ? 'active' : ''}><strong>{sub.label}</strong><em>{percent}%</em></span>; })}</div>}
      <div className="processing-actions"><button className="primary" onClick={loadMockReview}>{state.pipelineStatus === 'completed' ? '打开 Review 结果' : '使用已有结果'}</button>{state.pipelineStatus === 'running' && <button onClick={async () => { if (state.pipelineTaskId) await repository.cancelPipeline(state.pipelineTaskId); mutate((draft: any) => { draft.pipelineStatus = 'cancelled'; }); }}>取消分析</button>}</div>
    </section>
  </main>;
}

function normalizeStage(stage: string) {
  if (stage === 'thumbnail') return 'thumb';
  if (stage === 'quality') return 'iqa';
  if (stage === 'start') return 'scan';
  return stage;
}

function buildPipelineProgress(events: any[], groups: any[], status: string) {
  const stagePercents: Record<string, number> = {};
  const stageOrder = groups.flatMap((group) => group.stages.map((stage: any) => stage.key));
  let latest: any = null;
  for (const event of events || []) {
    const stage = normalizeStage(event?.stage);
    if (!stage) continue;
    const percent = Math.max(0, Math.min(100, Number(event.percent) || (event.total ? Math.round(((event.done || 0) / event.total) * 100) : 0)));
    stagePercents[stage] = Math.max(stagePercents[stage] || 0, percent);
    latest = { ...event, stage };
    const index = stageOrder.indexOf(stage);
    if (index > 0) {
      for (const previousStage of stageOrder.slice(0, index)) {
        stagePercents[previousStage] = 100;
      }
    }
  }
  if (status === 'completed') {
    for (const group of groups) for (const stage of group.stages) stagePercents[stage.key] = 100;
  }
  const groupPercents: Record<string, number> = {};
  for (const group of groups) {
    const sum = group.stages.reduce((total: number, stage: any) => total + (stagePercents[stage.key] || 0), 0);
    groupPercents[group.key] = Math.round(sum / group.stages.length);
  }
  const currentGroup = groups.find((group) => group.stages.some((stage: any) => stage.key === latest?.stage)) || groups.find((group) => groupPercents[group.key] < 100) || groups[groups.length - 1];
  const currentSubstage = currentGroup?.stages.find((stage: any) => stage.key === latest?.stage);
  const overallPercent = Math.round(groups.reduce((total, group) => total + groupPercents[group.key], 0) / groups.length);
  return { latest, stagePercents, groupPercents, currentGroup, currentSubstage, overallPercent };
}

function ReviewScreen({ state, mutate, saveDecision, saveDecisions, appendDecision, returnToStart }: any) {
  const [clusterCollapsed, setClusterCollapsed] = useState(false);
  const [compareInspectorOpen, setCompareInspectorOpen] = useState(false);
  useEffect(() => {
    if (!state.stagePlan) refreshStagePlan();
  }, [state.folder]);

  const refreshStagePlan = async () => {
    const nextPlan = await repository.dryRunStage(state.folder);
    mutate((draft: any) => { draft.stagePlan = nextPlan; });
  };
  return <main className={`review-shell ${clusterCollapsed ? 'cluster-collapsed' : ''} ${state.mode === 'compare' ? 'compare-mode' : ''} ${compareInspectorOpen ? 'compare-inspector-open' : ''}`}>
    <header className="topbar"><div className="topbar-title"><button className="back-project-button" title="返回主页面" aria-label="返回主页面" onClick={returnToStart}>‹</button><strong>Cullary</strong><span>{state.summary?.review_set_count || state.reviewSets.length} 组</span></div><div className="top-actions"><button onClick={() => mutate((d: any) => { d.mode = 'deck'; })}>组视图</button><button onClick={() => mutate((d: any) => { d.mode = 'grid'; })}>查看全部</button><button onClick={() => mutate((d: any) => { d.screen = 'staging'; })}>全局最终确认</button></div></header>
    <aside className="cluster-list"><button className="cluster-toggle" title={clusterCollapsed ? '展开分组' : '折叠分组'} aria-label={clusterCollapsed ? '展开分组' : '折叠分组'} onClick={() => setClusterCollapsed(!clusterCollapsed)}>{clusterCollapsed ? '›' : '‹'}</button><ClusterList state={state} mutate={mutate} collapsed={clusterCollapsed} /></aside>
    <section className="workspace">{state.lastAction && <div className="action-toast">{state.lastAction}</div>}{state.mode === 'compare' ? <CompareView state={state} mutate={mutate} appendDecision={appendDecision} /> : state.mode === 'grid' ? <GridView state={state} /> : <DeckView state={state} mutate={mutate} saveDecision={saveDecision} saveDecisions={saveDecisions} />}</section>
    <aside className="inspector">
      {state.mode === 'compare' && <button className="inspector-toggle" title={compareInspectorOpen ? '隐藏对比信息' : '显示对比信息'} aria-label={compareInspectorOpen ? '隐藏对比信息' : '显示对比信息'} onClick={() => setCompareInspectorOpen(!compareInspectorOpen)}>{compareInspectorOpen ? '›' : '‹'}</button>}
      {state.mode === 'compare' ? <CompareInspector state={state} /> : <Inspector state={state} mutate={mutate} saveDecision={saveDecision} refreshStagePlan={refreshStagePlan} />}
    </aside>
  </main>;
}

function ClusterList({ state, mutate, collapsed = false }: any) {
  return state.reviewSets.map((set: any, index: number) => {
    const cover = photoById(set, set.cover_display_id) || set.photos[0];
    const active = index === state.activeSetIndex;
    return <button key={set.review_set_id} className={`cluster-row ${active ? 'active' : ''}`} onClick={() => mutate((draft: any) => selectSet(draft, index))}>
      <Image state={state} photo={cover} />
      {!collapsed && <span><strong>{set.photo_count} 张</strong><small>{set.set_type}</small></span>}
    </button>;
  });
}

function DeckView({ state, mutate, saveDecision, saveDecisions }: any) {
  const set = activeSet(state);
  const selected = activePhoto(state);
  const keepers = keeperPhotos(state);
  const challengers = challengerPhotos(state);
  const selectedIds = state.selectedPhotoIds || new Set();
  const selectedPhotos = (set?.photos || []).filter((photo: any) => selectedIds.has(photo.display_id));
  const selectedState = decisionFor(state, selected);
  const canCompare = Boolean(activeKeeper(state) && activeChallenger(state));
  const actionPhotos = selectedPhotos.length ? selectedPhotos : selected ? [selected] : [];
  const actionLabel = selectedPhotos.length ? `${selectedPhotos.length} 张` : '当前图';
  const selectedPool = state.selectedPool;
  const toggleSelection = (event: any, photo: any, pool: string, orderedPhotos: any[]) => {
    event.stopPropagation();
    mutate((draft: any) => {
      const ids = orderedPhotos.map((item: any) => item.display_id);
      if (event.shiftKey) selectPhotoRange(draft, photo.display_id, pool, ids);
      else togglePhotoSelected(draft, photo.display_id, pool);
    });
  };
  return <div className="deck-view schema11-deck compact-deck">
    <section className="pool-section deck-pool keep-strip" aria-label="保留照片">
      <div className="pool-side-label">保留</div>
      <div className="keeper-slots pool-strip">{keepers.map((photo: any) => <PhotoCard key={photo.display_id} state={state} photo={photo} active={selected?.display_id === photo.display_id} selected={selectedIds.has(photo.display_id)} label="保留" onClick={(event: any) => event.shiftKey ? toggleSelection(event, photo, 'keep', keepers) : mutate((d: any) => selectKeeper(d, photo.display_id))} onToggle={(event: any) => toggleSelection(event, photo, 'keep', keepers)} />)}</div>
    </section>
    <div className={`hero-photo ${selectedState}`}>
      <ZoomablePhoto state={state} mutate={mutate} photo={selected} view={state.deckZoom || { scale: 1, x: 0, y: 0 }} update={(draft: any, updater: any) => updateDeckZoom(draft, updater)} />
      <button className="hero-reset-button" title="重置视图" aria-label="重置视图" onClick={() => mutate(resetDeckZoom)}>↺</button>
      <span className={`decision-pill ${selectedState}`}>{decisionLabel(selectedState)}{isAlternate(set, selected) ? ' · 备选' : ''}</span>
      <div className="deck-command-bar" aria-label="当前大图操作">
        <span>{actionLabel}</span>
        <button className="primary" disabled={!canCompare || selectedPhotos.length > 0} onClick={() => mutate((d: any) => { d.mode = 'compare'; })}>对比</button>
        <button className={selectedState === 'user_keep' && !selectedPhotos.length ? 'selected-action' : ''} disabled={!actionPhotos.length || selectedPool === 'keep'} onClick={() => selectedPhotos.length ? saveDecisions(selectedPhotos, 'user_keep', 'batch_keep') : saveDecision(selected, 'user_keep')}>保留</button>
        <button className={selectedState !== 'user_keep' && !selectedPhotos.length ? 'danger-action' : ''} disabled={!actionPhotos.length || selectedPool === 'delete'} onClick={() => selectedPhotos.length ? saveDecisions(selectedPhotos, 'user_challenger', 'batch_delete') : saveDecision(selected, 'user_challenger')}>待删</button>
        {selectedPhotos.length > 0 && <button className="ghost-action" onClick={() => mutate(clearPhotoSelection)}>取消选择</button>}
      </div>
    </div>
    <section className="pool-section deck-pool delete-strip" aria-label="待删除照片">
      <div className="pool-side-label danger-title">待删除</div>
      <div className="challenger-strip">{challengers.map((photo: any, index: number) => <ChallengerCard key={photo.display_id} state={state} photo={photo} index={index} active={selected?.display_id === photo.display_id} selected={selectedIds.has(photo.display_id)} onClick={(event: any) => event.shiftKey ? toggleSelection(event, photo, 'delete', challengers) : mutate((d: any) => selectChallenger(d, photo.display_id))} onToggle={(event: any) => toggleSelection(event, photo, 'delete', challengers)} />)}</div>
    </section>
  </div>;
}

function PhotoCard({ state, photo, active, selected, label, onClick, onToggle }: any) {
  const status = compactPhotoStatus(state, photo, label);
  return <button className={`deck-photo-card photo-card ${active ? 'active' : ''} ${selected ? 'multi-selected' : ''} ${decisionFor(state, photo)}`} onClick={onClick}>
    <span className={`select-check ${selected ? 'checked' : ''}`} role="checkbox" aria-checked={selected} title={selected ? '取消选择' : '选择'} onClick={onToggle}>{selected ? '✓' : ''}</span>
    <Image state={state} photo={photo} />
    <span><strong>{photo.display_id}</strong><small>{status}</small></span>
  </button>;
}

function ChallengerCard({ state, photo, index, active, selected, onClick, onToggle }: any) {
  const status = compactPhotoStatus(state, photo, `${index + 1}`);
  return <button className={`deck-challenger-card challenger ${active ? 'active' : ''} ${selected ? 'multi-selected' : ''} ${isAlternate(activeSet(state), photo) ? 'alternate' : ''}`} onClick={onClick}>
    <span className={`select-check ${selected ? 'checked' : ''}`} role="checkbox" aria-checked={selected} title={selected ? '取消选择' : '选择'} onClick={onToggle}>{selected ? '✓' : ''}</span>
    <Image state={state} photo={photo} />
    <span className="thumb-badge">{status}</span>
  </button>;
}

function compactPhotoStatus(state: any, photo: any, fallback: string) {
  const set = activeSet(state);
  const meta = challengerMeta(set, photo?.display_id);
  const delta = formatDelta(meta?.score_delta);
  const stateLabel = isAlternate(set, photo) ? '备选' : decisionFor(state, photo) === 'user_undecided' ? '待确认' : decisionLabel(decisionFor(state, photo));
  if (delta) return `${stateLabel} · Δ ${delta}`;
  return stateLabel || fallback;
}
function GridView({ state }: any) {
  const set = activeSet(state);
  return <div className="grid-view">{set.photos.map((photo: any) => { const value = decisionFor(state, photo); return <button key={photo.display_id} className={`photo-tile ${value}`}><Image state={state} photo={photo} /><span>{photo.rank}. {photo.display_id}</span><small>{decisionLabel(value)}{isAlternate(set, photo) ? ' · 备选' : ''}</small></button>; })}</div>;
}

function CompareView({ state, mutate, appendDecision }: any) {
  const keeper = activeKeeper(state); const challenger = activeChallenger(state);
  useEffect(() => {
    if (!keeper || !challenger) {
      mutate((draft: any) => { draft.mode = 'deck'; });
    }
  }, [keeper?.display_id, challenger?.display_id]);
  if (!keeper || !challenger) return <div className="empty">本组已无待删除照片。</div>;
  const keeperRatio = keeper.preview_width / Math.max(keeper.preview_height, 1);
  const challengerRatio = challenger.preview_width / Math.max(challenger.preview_height, 1);
  const layout = keeperRatio >= 1.7 && challengerRatio >= 1.7 ? 'stacked' : 'side-by-side';
  const persistChange = (draft: any, photo: any, userState: string, previous: string, source: string) => appendDecision(draft, photo, userState, previous, source);
  const replace = () => mutate((draft: any) => {
    const result = replaceWithChallenger(draft);
    if (!result) return;
    repository.appendPreferenceEvent(draft.folder, { review_set_id: activeSet(draft).review_set_id, keeper_photo_id: result.keeper.display_id, challenger_photo_id: result.challenger.display_id, decision: 'replace' });
    persistChange(draft, result.keeper, 'user_challenger', result.previousKeeper, 'replace');
    persistChange(draft, result.challenger, 'user_keep', result.previousChallenger, 'replace');
    draft.stagePlan = null;
    draft.lastAction = `${result.challenger.display_id}: 已替换保留`;
  });
  const keepBothAction = () => mutate((draft: any) => {
    const result = keepBoth(draft);
    if (!result) return;
    repository.appendPreferenceEvent(draft.folder, { review_set_id: activeSet(draft).review_set_id, keeper_photo_id: result.keeper.display_id, challenger_photo_id: result.challenger.display_id, decision: 'keep_both' });
    persistChange(draft, result.keeper, 'user_keep', result.previousKeeper, 'keep_both');
    persistChange(draft, result.challenger, 'user_keep', result.previousChallenger, 'keep_both');
    draft.stagePlan = null;
    draft.lastAction = `${result.challenger.display_id}: 已加入保留`;
  });
  return <div className={`compare-view ${layout}`}><div className="compare-toolbar"><div className="compare-decision-actions"><button className="primary" onClick={replace}>替换保留</button><button onClick={keepBothAction}>两张都保留</button></div><div className="compare-nav-actions"><button onClick={() => mutate(previousChallenger)}>上一张</button><button onClick={() => mutate(nextChallenger)}>下一张</button><button onClick={() => mutate((d: any) => { d.compare.linked = !d.compare.linked; })}>{state.compare.linked ? '同步开' : '同步关'}</button><button onClick={() => mutate(resetZoom)}>重置</button><button onClick={() => mutate((d: any) => { d.mode = 'deck'; })}>返回</button></div></div><ComparePane state={state} mutate={mutate} side="left" photo={keeper} label="保留" /><ComparePane state={state} mutate={mutate} side="right" photo={challenger} label="待删除" /></div>;
}

function ComparePane({ state, mutate, side, photo, label }: any) {
  const view = state.compare.linked ? state.compare : state.compare[side];
  return <div className={`compare-pane ${decisionFor(state, photo)}`}><div className="compare-pane-label"><strong>{label}</strong><span>{photo.display_id}</span><em>{decisionLabel(decisionFor(state, photo))}</em></div><ZoomablePhoto state={state} mutate={mutate} photo={photo} view={view} update={(draft: any, updater: any) => updateZoom(draft, side, updater)} /></div>;
}

function ZoomablePhoto({ state, mutate, photo, view, update }: any) {
  const [drag, setDrag] = useState<any>(null);
  const surfaceRef = useRef<HTMLDivElement | null>(null);
  const [fitSize, setFitSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const element = surfaceRef.current;
    if (!element || !photo) return;
    const measure = () => {
      const rect = element.getBoundingClientRect();
      const imageWidth = Number(photo.preview_width) || 1;
      const imageHeight = Number(photo.preview_height) || 1;
      const fit = Math.min(rect.width / imageWidth, rect.height / imageHeight);
      setFitSize({ width: imageWidth * fit, height: imageHeight * fit });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [photo?.display_id, photo?.preview_width, photo?.preview_height]);
  return <div ref={surfaceRef} className="zoom-surface" onWheel={(event) => { event.preventDefault(); const factor = event.deltaY < 0 ? 1.04 : 0.96; mutate((d: any) => update(d, (v: any) => ({ ...v, scale: Math.max(1, Math.min(6, v.scale * factor)) }))); }} onPointerDown={(event) => setDrag({ x: event.clientX, y: event.clientY })} onPointerMove={(event) => { if (!drag) return; const dx = event.clientX - drag.x; const dy = event.clientY - drag.y; setDrag({ x: event.clientX, y: event.clientY }); mutate((d: any) => update(d, (v: any) => ({ ...v, x: v.x + dx, y: v.y + dy }))); }} onPointerUp={() => setDrag(null)} onPointerLeave={() => setDrag(null)}>
    <div className="zoom-content" style={{ width: `${fitSize.width}px`, height: `${fitSize.height}px`, transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}><Image state={state} photo={photo} kind="preview" /></div>
  </div>;
}

function Inspector({ state, mutate, saveDecision, refreshStagePlan }: any) {
  const set = activeSet(state); const photo = activePhoto(state); const value = decisionFor(state, photo); const meta = challengerMeta(set, photo?.display_id); const keepers = keeperPhotos(state);
  const totalBytes = sourceBytesForPhotos(set.photos || []);
  const keepBytes = sourceBytesForPhotos(keepers);
  const done = isSetCompleted(state, set);
  const toggleCompleted = () => {
    const nextCompleted = new Set(state.completedSets || []);
    if (nextCompleted.has(set.review_set_id)) nextCompleted.delete(set.review_set_id);
    else nextCompleted.add(set.review_set_id);
    repository.saveReviewProgress(state.folder, { schema_version: '1.0', completed_review_set_ids: [...nextCompleted] });
    mutate((draft: any) => { draft.completedSets = nextCompleted; });
  };
  return <div className="reason-card deck-inspector"><p className="eyebrow">本组进度</p><div className="simple-ratio"><strong>{keepers.length}/{set.photo_count}</strong><span>已保留 · {formatBytes(keepBytes)} / {formatBytes(totalBytes)}</span></div><button className={done ? 'wide selected-action' : 'wide'} onClick={toggleCompleted}>{done ? '本组已完成' : '标记本组完成'}</button><hr /><p className="eyebrow">当前大图</p><h3>{photo.display_id}</h3><div className="current-decision-row"><span className={`state-line ${value}`}>{decisionLabel(value)}{isAlternate(set, photo) ? ' · 备选' : ''}</span><strong>{scoreText(photo)}</strong></div>{meta && <p className="muted">相似度 {Math.round((meta.similarity_to_primary || 0) * 100)} · 分差 {formatDelta(meta.score_delta) || '—'}</p>}<p className="eyebrow">保留依据</p><ReasonList items={photo.reason_summary_zh} /><p className="eyebrow">主要弱点</p><ReasonList items={photo.weakness_summary_zh} /></div>;
}

function RadarChart({ dimensions }: any) {
  const size = 188; const center = size / 2; const radius = 58;
  const polygonPoints = (side: 'left' | 'right') => dimensions.map((item: any, index: number) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / dimensions.length;
    const value = Math.max(0, Math.min(100, item[side])) / 100;
    return `${center + Math.cos(angle) * radius * value},${center + Math.sin(angle) * radius * value}`;
  }).join(' ');
  const gridPoints = (scale: number) => dimensions.map((_: any, index: number) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / dimensions.length;
    return `${center + Math.cos(angle) * radius * scale},${center + Math.sin(angle) * radius * scale}`;
  }).join(' ');
  if (!dimensions.length) return null;
  return <div className="radar-wrap"><svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label="绝对质量雷达图">
    {[0.33, 0.66, 1].map((scale) => <polygon key={scale} className="radar-grid" points={gridPoints(scale)} />)}
    {dimensions.map((item: any, index: number) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / dimensions.length;
      return <g key={item.key}><line className="radar-axis" x1={center} y1={center} x2={center + Math.cos(angle) * radius} y2={center + Math.sin(angle) * radius} /><text x={center + Math.cos(angle) * (radius + 28)} y={center + Math.sin(angle) * (radius + 28)} textAnchor="middle" dominantBaseline="middle">{item.label.replace('质量', '')} {item.left}→{item.right}</text></g>;
    })}
    <polygon className="radar-left" points={polygonPoints('left')} />
    <polygon className="radar-right" points={polygonPoints('right')} />
  </svg><div className="chart-legend"><span><i className="legend-left" />保留</span><span><i className="legend-right" />待删除</span></div></div>;
}

function HistogramCompare({ left, right }: any) {
  const [channel, setChannel] = useState<'luma' | 'r' | 'g' | 'b' | 'rgb'>('luma');
  const leftLum = brightnessHistogram(left); const rightLum = brightnessHistogram(right);
  const leftRgb = rgbHistogram(left); const rightRgb = rgbHistogram(right);
  if (!leftLum.length || !rightLum.length) return null;
  const leftClip = clipText(left); const rightClip = clipText(right);
  return <div className="histogram-card"><div className="histogram-head"><p className="eyebrow">直方图对比</p><div className="histogram-toggle">{(['luma', 'r', 'g', 'b', 'rgb'] as const).map((item) => <button key={item} className={channel === item ? 'active' : ''} onClick={() => setChannel(item)}>{item === 'luma' ? '亮度' : item.toUpperCase()}</button>)}</div></div><CombinedHistogram leftLum={leftLum} rightLum={rightLum} leftRgb={leftRgb} rightRgb={rightRgb} channel={channel} /><div className="histogram-meta"><span>保留：{leftClip || '—'}</span><span>待删除：{rightClip || '—'}</span></div><div className="histogram-axis"><span>暗部</span><span>中间调</span><span>高光</span></div></div>;
}

function CombinedHistogram({ leftLum, rightLum, leftRgb, rightRgb, channel }: any) {
  const width = 260; const height = 92;
  const channelSeries = channel === 'rgb'
    ? [leftRgb?.r || [], leftRgb?.g || [], leftRgb?.b || [], rightRgb?.r || [], rightRgb?.g || [], rightRgb?.b || []]
    : channel === 'luma'
      ? [leftLum, rightLum]
      : [leftRgb?.[channel] || [], rightRgb?.[channel] || []];
  const series = channelSeries.filter((arr) => arr.length);
  const maxValue = Math.max(...series.flat(), 0.001);
  return <svg className="combined-histogram" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="histogram compare">
    <line className="hist-grid" x1={width / 3} y1="0" x2={width / 3} y2={height} />
    <line className="hist-grid" x1={width * 2 / 3} y1="0" x2={width * 2 / 3} y2={height} />
    {channel === 'luma' ? <>
      <path className="hist-luma-fill left" d={histogramPath(leftLum, width, height, maxValue, true)} />
      <path className="hist-luma-fill right" d={histogramPath(rightLum, width, height, maxValue, true)} />
      <path className="hist-luma left" d={histogramPath(leftLum, width, height, maxValue)} />
      <path className="hist-luma right" d={histogramPath(rightLum, width, height, maxValue)} />
    </> : channel === 'rgb' ? <>
      {leftRgb?.r && <path className="hist-r left" d={histogramPath(leftRgb.r, width, height, maxValue)} />}
      {leftRgb?.g && <path className="hist-g left" d={histogramPath(leftRgb.g, width, height, maxValue)} />}
      {leftRgb?.b && <path className="hist-b left" d={histogramPath(leftRgb.b, width, height, maxValue)} />}
      {rightRgb?.r && <path className="hist-r right" d={histogramPath(rightRgb.r, width, height, maxValue)} />}
      {rightRgb?.g && <path className="hist-g right" d={histogramPath(rightRgb.g, width, height, maxValue)} />}
      {rightRgb?.b && <path className="hist-b right" d={histogramPath(rightRgb.b, width, height, maxValue)} />}
    </> : <>
      {leftRgb?.[channel] && <path className={`hist-${channel} left`} d={histogramPath(leftRgb[channel], width, height, maxValue)} />}
      {rightRgb?.[channel] && <path className={`hist-${channel} right`} d={histogramPath(rightRgb[channel], width, height, maxValue)} />}
    </>}
  </svg>;
}

function histogramPath(values: number[], width: number, height: number, maxValue: number, area = false) {
  if (!values.length) return '';
  const step = width / Math.max(values.length - 1, 1);
  const points = values.map((value, index) => `${index * step},${height - Math.max(0, value) / maxValue * (height - 6) - 3}`);
  const line = `M ${points.join(' L ')}`;
  return area ? `${line} L ${width},${height} L 0,${height} Z` : line;
}

function CompareInspector({ state }: any) {
  const keeper = activeKeeper(state); const challenger = activeChallenger(state); const set = activeSet(state); const meta = challengerMeta(set, challenger?.display_id);
  const dimensions = scoreDimensions(keeper, challenger);
  const metricRows = compareMetricRows(keeper, challenger);
  const [expanded, setExpanded] = useState(false);
  const shownRows = expanded ? metricRows : metricRows.slice(0, 5);
  const diff = meta?.score_delta;
  return <div className="reason-card"><p className="eyebrow">对比参数</p><div className="compare-stats"><div><strong>保留</strong><span>{keeper?.display_id || '—'}</span><em>推荐分 {scoreText(keeper)}</em><em>绝对质量 {baseScoreText(keeper)}</em><em>{keeper?.preview_width}×{keeper?.preview_height}</em><em>{formatBytes(photoBytes(keeper))}</em></div><div><strong>待删除</strong><span>{challenger?.display_id || '—'}</span><em>推荐分 {scoreText(challenger)}</em><em>绝对质量 {baseScoreText(challenger)}</em><em>{challenger?.preview_width}×{challenger?.preview_height}</em><em>{formatBytes(photoBytes(challenger))}</em></div></div>{meta && <p className="muted">相似度 {Math.round((meta.similarity_to_primary || 0) * 100)} · 推荐分差 {formatDelta(diff) || '—'} · {meta.reason_zh || ''}</p>}<div className="score-diff-list"><p className="eyebrow">绝对质量维度</p><RadarChart dimensions={dimensions} /></div><div className="score-diff-list"><div className="section-head"><p className="eyebrow">关键子项</p>{metricRows.length > 5 && <button className="link-action icon-only" title={expanded ? '收起' : '展开全部'} aria-label={expanded ? '收起' : '展开全部'} onClick={() => setExpanded(!expanded)}>{expanded ? '⌃' : '⌄'}</button>}</div>{shownRows.map((item: any) => <div className="score-diff-row metric-row" key={item.key}><span><small>{item.group}</small>{item.label}</span><strong>{item.left}</strong><em className={item.diff >= 0 ? 'better' : 'worse'}>{item.diff > 0 ? '+' : ''}{item.diff}</em><strong>{item.right}</strong></div>)}</div><HistogramCompare left={keeper} right={challenger} /></div>;
}


function StagingScreen({ state, mutate, returnToStart }: any) {
  const deleteCount = allDeletePhotos(state).length;
  const totalCount = allReviewPhotos(state).length;
  const plan = state.stagePlan;
  const result = state.stageResult;
  const completedCount = state.completedSets?.size || 0;
  const targetDelete = plan?.target_delete_count ?? deleteCount;
  const targetKeep = plan?.target_keep_count ?? (totalCount - deleteCount);
  const moveToDelete = plan?.move_to_delete_count ?? 0;
  const restoreKeep = plan?.restore_keep_count ?? 0;
  const alreadyStaged = plan?.already_staged_count ?? 0;
  const alreadyKept = plan?.already_kept_count ?? 0;
  return <main className="staging-screen"><section className="start-panel"><p className="eyebrow">全局最终确认</p><h2>最终待删除 {targetDelete} / {totalCount} 张</h2><p>这是对当前文件夹的全部 Review 结果生效，不是只处理当前 cluster。</p><p>已标记完成 {completedCount}/{state.reviewSets.length} 组；未完成也可以最终确认，但建议先逐组确认。</p><p>待删除照片会移动到 <code>.to_delete/</code>，不会永久删除。</p>{plan && <div className="stage-summary"><p><strong>最终状态</strong>：保留 {targetKeep} 张，待删除 {targetDelete} 张</p><p><strong>本次变更</strong>：移入 .to_delete {moveToDelete} 张，恢复保留 {restoreKeep} 张</p><p><strong>无需移动</strong>：已在 .to_delete {alreadyStaged} 张，已在原位 {alreadyKept} 张</p><p>保留空间：{formatBytes(plan.keep_source_bytes)} / {formatBytes(plan.all_source_bytes)}，释放 {formatBytes(plan.source_bytes)}</p><p>Sidecar 本次移动：{plan.sidecar_count} 个；问题：{plan.issues?.length || 0}</p></div>}{result && <div className="stage-summary"><p>批次： <code>{result.operation_batch_id}</code></p><p>实际文件操作： {result.moved_count}，失败： {result.failed_count}</p></div>}<div className="stage-actions"><button onClick={() => mutate((draft: any) => { draft.screen = 'review'; })}>返回 Review</button><button onClick={returnToStart}>切换项目</button><button onClick={async () => { const nextPlan = await repository.dryRunStage(state.folder); mutate((draft: any) => { draft.stagePlan = nextPlan; draft.stageResult = null; }); }}>重新计算</button><button className="primary" disabled={!plan} onClick={async () => { const nextResult = await repository.executeStage(state.folder, plan.plan_id); mutate((draft: any) => { draft.stageResult = nextResult; }); }}>应用本次变更</button>{result?.operation_batch_id && <button onClick={async () => { const undo = await repository.undoStage(state.folder, result.operation_batch_id); mutate((draft: any) => { draft.stageResult = { ...undo, moved_count: undo.restored_count }; }); }}>撤销</button>}</div></section></main>;
}

function Image({ state, photo, kind = 'thumb', className = '' }: any) {
  const artifactPath = kind === 'preview' ? photo.preview_path : photo.thumb_path;
  const [src, setSrc] = useState(() => resolveAssetPath(state.folder, artifactPath));
  const [didFallback, setDidFallback] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const width = kind === 'preview' ? photo.preview_width : photo.thumb_width;
  const height = kind === 'preview' ? photo.preview_height : photo.thumb_height;
  useEffect(() => {
    setSrc(resolveAssetPath(state.folder, artifactPath));
    setDidFallback(false);
    setLoadError(null);
  }, [state.folder, artifactPath, photo.display_id, kind]);
  return <span className={`image-frame image-${kind} ${className}`}>
    <img
      src={src}
      width={width}
      height={height}
      alt={photo.display_id}
      loading="lazy"
      decoding="async"
      onLoad={() => { if (didFallback) console.info('[Cullary image] loaded via fallback', { displayId: photo.display_id, kind }); }}
      onError={async () => {
        console.warn('[Cullary image] failed', { displayId: photo.display_id, kind, artifactPath, src, didFallback });
        if (didFallback) { setLoadError('image load failed'); return; }
        setDidFallback(true);
        try { setSrc(await repository.readImageDataUrl(state.folder, artifactPath)); } catch (error) { console.warn('[Cullary image] fallback failed', photo.display_id, error); setLoadError(String(error)); }
      }}
    />
    {loadError && <small className="image-error">{loadError}</small>}
  </span>;
}

function ReasonList({ items = [] }: any) {
  return items.length ? <ul>{items.map((item: string) => <li key={item}>{item}</li>)}</ul> : <p className="muted">—</p>;
}
