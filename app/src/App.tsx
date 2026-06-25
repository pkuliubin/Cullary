import React, { useEffect, useState } from 'react';
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
  selectChallenger,
  selectKeeper,
  selectSet,
  setDecisionState,
  updateZoom,
  applyPersistedDecisions,
  applyReviewProgress,
} from './reviewState.js';

function cloneState(state: any) {
  return { ...state, decisions: new Map(state.decisions), completedSets: new Set(state.completedSets || []), compare: { ...state.compare, left: { ...state.compare.left }, right: { ...state.compare.right } } };
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
  group_relative: '组内相对',
};

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
    .sort((a: any, b: any) => Math.abs(b.diff) - Math.abs(a.diff));
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
  if (state.screen === 'review' && set) return <ReviewScreen state={state} mutate={mutate} saveDecision={saveDecision} appendDecision={appendDecision} />;
  if (state.screen === 'staging') return <StagingScreen state={state} mutate={mutate} />;
  return <StartScreen state={state} mutate={mutate} loadMockReview={loadMockReview} />;
}

function StartScreen({ state, mutate, loadMockReview }: any) {
  return <main className="start-screen">
    <section className="start-copy"><p className="eyebrow">本地照片筛选工作台</p><h1>Cullary</h1><p>把连拍和相似照片整理成一组，先给出建议，再由你快速决定保留哪些。</p></section>
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

function ReviewScreen({ state, mutate, saveDecision, appendDecision }: any) {
  useEffect(() => {
    if (!state.stagePlan) refreshStagePlan();
  }, [state.folder]);

  const refreshStagePlan = async () => {
    const nextPlan = await repository.dryRunStage(state.folder);
    mutate((draft: any) => { draft.stagePlan = nextPlan; });
  };
  return <main className="review-shell">
    <header className="topbar"><div><strong>Cullary</strong><span>{state.summary?.review_set_count || state.reviewSets.length} 组</span></div><div className="top-actions"><button onClick={() => mutate((d: any) => { d.mode = 'deck'; })}>组视图</button><button onClick={() => mutate((d: any) => { d.mode = 'grid'; })}>查看全部</button><button onClick={() => mutate((d: any) => { d.screen = 'staging'; })}>全局最终确认</button></div></header>
    <aside className="cluster-list"><ClusterList state={state} mutate={mutate} /></aside>
    <section className="workspace">{state.lastAction && <div className="action-toast">{state.lastAction}</div>}{state.mode === 'compare' ? <CompareView state={state} mutate={mutate} /> : state.mode === 'grid' ? <GridView state={state} /> : <DeckView state={state} mutate={mutate} saveDecision={saveDecision} />}</section>
    <aside className="inspector">{state.mode === 'compare' ? <CompareInspector state={state} mutate={mutate} appendDecision={appendDecision} /> : <Inspector state={state} mutate={mutate} saveDecision={saveDecision} refreshStagePlan={refreshStagePlan} />}</aside>
  </main>;
}

function ClusterList({ state, mutate }: any) {
  return state.reviewSets.map((set: any, index: number) => {
    const cover = photoById(set, set.cover_display_id) || set.photos[0];
    const active = index === state.activeSetIndex;
    return <button key={set.review_set_id} className={`cluster-row ${active ? 'active' : ''}`} onClick={() => mutate((draft: any) => selectSet(draft, index))}>
      <Image state={state} photo={cover} />
      <span><strong>{set.photo_count} 张</strong><small>{set.set_type}</small></span>
    </button>;
  });
}

function DeckView({ state, mutate, saveDecision }: any) {
  const set = activeSet(state);
  const selected = activePhoto(state);
  const keepers = keeperPhotos(state);
  const challengers = challengerPhotos(state);
  const selectedState = decisionFor(state, selected);
  return <div className="deck-view schema11-deck">
    <section className="pool-section"><div className="pool-title"><strong>保留</strong><span>当前决定保留的照片</span></div><div className="keeper-slots pool-strip">{keepers.map((photo: any) => <PhotoCard key={photo.display_id} state={state} photo={photo} active={selected?.display_id === photo.display_id} label="保留" onClick={() => mutate((d: any) => selectKeeper(d, photo.display_id))} extra={<button className="mini-action" onClick={(event) => { event.stopPropagation(); saveDecision(photo, 'user_challenger', 'move_to_delete'); }}>待删除</button>} />)}</div></section>
    <div className={`hero-photo ${selectedState}`}>
      <Image state={state} photo={selected} kind="preview" className="preview-image" />
      <span className={`decision-pill ${selectedState}`}>{decisionLabel(selectedState)}{isAlternate(set, selected) ? ' · 备选' : ''}</span>
    </div>
    <section className="pool-section"><div className="pool-title"><strong>待删除</strong><span>确认后会移入安全暂存区</span></div><div className="challenger-strip">{challengers.map((photo: any, index: number) => <ChallengerCard key={photo.display_id} state={state} photo={photo} index={index} active={selected?.display_id === photo.display_id} onClick={() => mutate((d: any) => selectChallenger(d, photo.display_id))} />)}</div></section>
    <div className="deck-actions review-action-bar"><button className={selectedState === 'user_keep' ? 'selected-action' : ''} disabled={!selected} onClick={() => saveDecision(selected, 'user_keep')}>保留</button><button className={selectedState !== 'user_keep' ? 'danger-action' : ''} disabled={!selected} onClick={() => saveDecision(selected, 'user_challenger')}>待删除</button><button className="primary" disabled={!activeKeeper(state) || !activeChallenger(state)} onClick={() => mutate((d: any) => { d.mode = 'compare'; })}>进入对比</button></div>
  </div>;
}

function PhotoCard({ state, photo, active, label, onClick, extra }: any) {
  return <button className={`photo-card ${active ? 'active' : ''} ${decisionFor(state, photo)}`} onClick={onClick}>
    <Image state={state} photo={photo} />
    <span><strong>{photo.display_id}</strong><small>{label} · 评分 {scoreText(photo)}</small></span>
    {extra}
  </button>;
}

function ChallengerCard({ state, photo, index, active, onClick }: any) {
  const set = activeSet(state);
  const meta = challengerMeta(set, photo.display_id);
  const delta = formatDelta(meta?.score_delta);
  return <button className={`challenger ${active ? 'active' : ''} ${isAlternate(set, photo) ? 'alternate' : ''}`} onClick={onClick}>
    <Image state={state} photo={photo} />
    <span className="thumb-badge">{index + 1} · {isAlternate(set, photo) ? '备选' : decisionLabel(decisionFor(state, photo))}</span>
    <small>{delta ? `Δ ${delta}` : `评分 ${scoreText(photo)}`}</small>
  </button>;
}

function GridView({ state }: any) {
  const set = activeSet(state);
  return <div className="grid-view">{set.photos.map((photo: any) => { const value = decisionFor(state, photo); return <button key={photo.display_id} className={`photo-tile ${value}`}><Image state={state} photo={photo} /><span>{photo.rank}. {photo.display_id}</span><small>{decisionLabel(value)}{isAlternate(set, photo) ? ' · 备选' : ''}</small></button>; })}</div>;
}

function CompareView({ state, mutate }: any) {
  const keeper = activeKeeper(state); const challenger = activeChallenger(state);
  if (!keeper || !challenger) return <div className="empty">本组已无待删除照片。</div>;
  const keeperRatio = keeper.preview_width / Math.max(keeper.preview_height, 1);
  const challengerRatio = challenger.preview_width / Math.max(challenger.preview_height, 1);
  const layout = keeperRatio >= 1.7 && challengerRatio >= 1.7 ? 'stacked' : 'side-by-side';
  return <div className={`compare-view ${layout}`}><div className="compare-toolbar"><button onClick={() => mutate(previousChallenger)}>上一张</button><button onClick={() => mutate(nextChallenger)}>下一张</button><button onClick={() => mutate((d: any) => { d.compare.linked = !d.compare.linked; })}>{state.compare.linked ? '同步开' : '同步关'}</button><button onClick={() => mutate(resetZoom)}>重置</button><button onClick={() => mutate((d: any) => { d.mode = 'deck'; })}>返回</button></div><ComparePane state={state} mutate={mutate} side="left" photo={keeper} label="保留" /><ComparePane state={state} mutate={mutate} side="right" photo={challenger} label="待删除" /></div>;
}

function ComparePane({ state, mutate, side, photo, label }: any) {
  const view = state.compare.linked ? state.compare : state.compare[side];
  const [drag, setDrag] = useState<any>(null);
  return <div className={`compare-pane ${decisionFor(state, photo)}`} onWheel={(event) => { event.preventDefault(); const factor = event.deltaY < 0 ? 1.025 : 0.975; mutate((d: any) => updateZoom(d, side, (v: any) => ({ ...v, scale: Math.max(1, Math.min(4, v.scale * factor)) }))); }} onPointerDown={(event) => setDrag({ x: event.clientX, y: event.clientY })} onPointerMove={(event) => { if (!drag) return; const dx = event.clientX - drag.x; const dy = event.clientY - drag.y; setDrag({ x: event.clientX, y: event.clientY }); mutate((d: any) => updateZoom(d, side, (v: any) => ({ ...v, x: v.x + dx, y: v.y + dy }))); }} onPointerUp={() => setDrag(null)} onPointerLeave={() => setDrag(null)}><div className="compare-pane-label"><strong>{label}</strong><span>{photo.display_id}</span><em>{decisionLabel(decisionFor(state, photo))}</em></div><div className="zoom-surface" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}><Image state={state} photo={photo} kind="preview" /></div></div>;
}

function Inspector({ state, mutate, saveDecision, refreshStagePlan }: any) {
  const set = activeSet(state); const photo = activePhoto(state); const value = decisionFor(state, photo); const meta = challengerMeta(set, photo?.display_id); const keepers = keeperPhotos(state); const deletes = deletePhotos(state);
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
  return <div className="reason-card"><p className="eyebrow">本组</p><div className="simple-ratio"><strong>{keepers.length}/{set.photo_count}</strong><span>已保留 / 本组照片</span></div><p className="muted">保留空间：{formatBytes(keepBytes)} / {formatBytes(totalBytes)}</p><p className="muted">当前有 {deletes.length} 张标记为待删除。应用最终确认后，它们会移入安全暂存区，仍可撤销。</p><button className={done ? 'wide selected-action' : 'wide'} onClick={toggleCompleted}>{done ? '本组已完成' : '标记本组完成'}</button><button className="wide" onClick={refreshStagePlan}>重新计算全局空间</button><hr /><p className="eyebrow">当前照片</p><h3>{photo.display_id}</h3><p className={`state-line ${value}`}>{decisionLabel(value)}{isAlternate(set, photo) ? ' · 备选' : ''}</p>{meta && <p className="muted">相似度 {Math.round((meta.similarity_to_primary || 0) * 100)} · 分差 {formatDelta(meta.score_delta) || '—'}</p>}<ReasonList items={photo.reason_summary_zh} /><p className="eyebrow">弱点</p><ReasonList items={photo.weakness_summary_zh} /><p className="score">评分 {scoreText(photo)}</p></div>;
}

function CompareInspector({ state, mutate, appendDecision }: any) {
  const keeper = activeKeeper(state); const challenger = activeChallenger(state); const set = activeSet(state); const meta = challengerMeta(set, challenger?.display_id);
  const dimensions = scoreDimensions(keeper, challenger);
  const persistChange = (draft: any, photo: any, userState: string, previous: string, source: string) => appendDecision(draft, photo, userState, previous, source);
  const replace = () => mutate((draft: any) => {
    const result = replaceWithChallenger(draft);
    if (!result) return;
    repository.appendPreferenceEvent(draft.folder, { review_set_id: activeSet(draft).review_set_id, keeper_photo_id: result.keeper.display_id, challenger_photo_id: result.challenger.display_id, decision: 'replace' });
    persistChange(draft, result.keeper, 'user_challenger', result.previousKeeper, 'replace');
    persistChange(draft, result.challenger, 'user_keep', result.previousChallenger, 'replace');
    draft.stagePlan = null;
    draft.lastAction = `${result.challenger.display_id}: 已设为保留`;
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
  const keepDelete = () => mutate((draft: any) => {
    const current = activeChallenger(draft);
    if (!current) return;
    draft.lastAction = `${current.display_id}: 保持待删除`;
    nextChallenger(draft);
  });
  const diff = meta?.score_delta;
  return <div className="reason-card"><p className="eyebrow">对比参数</p><div className="compare-stats"><div><strong>保留</strong><span>{keeper?.display_id || '—'}</span><em>评分 {scoreText(keeper)}</em><em>{keeper?.preview_width}×{keeper?.preview_height}</em><em>{formatBytes(photoBytes(keeper))}</em></div><div><strong>待删除</strong><span>{challenger?.display_id || '—'}</span><em>评分 {scoreText(challenger)}</em><em>{challenger?.preview_width}×{challenger?.preview_height}</em><em>{formatBytes(photoBytes(challenger))}</em></div></div>{meta && <p className="muted">相似度 {Math.round((meta.similarity_to_primary || 0) * 100)} · 评分差 {formatDelta(diff) || '—'} · {meta.reason_zh || ''}</p>}<div className="score-diff-list"><p className="eyebrow">评分差异</p>{dimensions.slice(0, 5).map((item: any) => <div className="score-diff-row" key={item.key}><span>{item.label}</span><strong>{item.left}</strong><em className={item.diff >= 0 ? 'better' : 'worse'}>{item.diff > 0 ? '+' : ''}{item.diff}</em><strong>{item.right}</strong></div>)}</div><button className="primary wide" disabled={!challenger} onClick={replace}>替换保留</button><button className="wide" disabled={!challenger} onClick={keepBothAction}>两张都保留</button><button className="wide danger-action" disabled={!challenger} onClick={keepDelete}>保持待删除</button><p className="muted">缩放和平移会在上一张/下一张之间保持，用来连续检查细节。</p></div>;
}


function StagingScreen({ state, mutate }: any) {
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
  return <main className="staging-screen"><section className="start-panel"><p className="eyebrow">全局最终确认</p><h2>最终待删除 {targetDelete} / {totalCount} 张</h2><p>这是对当前文件夹的全部 Review 结果生效，不是只处理当前 cluster。</p><p>已标记完成 {completedCount}/{state.reviewSets.length} 组；未完成也可以最终确认，但建议先逐组确认。</p><p>待删除照片会移动到 <code>.to_delete/</code>，不会永久删除。</p>{plan && <div className="stage-summary"><p><strong>最终状态</strong>：保留 {targetKeep} 张，待删除 {targetDelete} 张</p><p><strong>本次变更</strong>：移入 .to_delete {moveToDelete} 张，恢复保留 {restoreKeep} 张</p><p><strong>无需移动</strong>：已在 .to_delete {alreadyStaged} 张，已在原位 {alreadyKept} 张</p><p>保留空间：{formatBytes(plan.keep_source_bytes)} / {formatBytes(plan.all_source_bytes)}，释放 {formatBytes(plan.source_bytes)}</p><p>Sidecar 本次移动：{plan.sidecar_count} 个；问题：{plan.issues?.length || 0}</p></div>}{result && <div className="stage-summary"><p>批次： <code>{result.operation_batch_id}</code></p><p>实际文件操作： {result.moved_count}，失败： {result.failed_count}</p></div>}<div className="stage-actions"><button onClick={() => mutate((draft: any) => { draft.screen = 'review'; })}>返回 Review</button><button onClick={async () => { const nextPlan = await repository.dryRunStage(state.folder); mutate((draft: any) => { draft.stagePlan = nextPlan; draft.stageResult = null; }); }}>重新计算</button><button className="primary" disabled={!plan} onClick={async () => { const nextResult = await repository.executeStage(state.folder, plan.plan_id); mutate((draft: any) => { draft.stageResult = nextResult; }); }}>应用本次变更</button>{result?.operation_batch_id && <button onClick={async () => { const undo = await repository.undoStage(state.folder, result.operation_batch_id); mutate((draft: any) => { draft.stageResult = { ...undo, moved_count: undo.restored_count }; }); }}>撤销</button>}</div></section></main>;
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
