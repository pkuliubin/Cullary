import { mockFolder, mockReviewSets, mockSummary } from '../mock/mockReviewData.js';
import { convertFileSrc } from '@tauri-apps/api/core';

const hasTauri = () => Boolean(window.isTauri || window.__TAURI_INTERNALS__);

const mockDecisions = [];
const mockProgress = { schema_version: '1.0', completed_review_set_ids: [] };

async function invoke(command, args = {}) {
  const api = await import('@tauri-apps/api/core');
  return api.invoke(command, args);
}

export function resolveAssetPath(folder, artifactPath) {
  if (!artifactPath) return '';
  if (/^(file|https?):/.test(artifactPath)) return artifactPath;
  const path = artifactPath.startsWith('/') ? artifactPath : `${folder}/${artifactPath}`;
  if (hasTauri()) {
    return convertFileSrc(path, 'asset');
  }
  return `file://${path}`;
}

export const repository = {
  async chooseFolder() {
    if (!hasTauri()) return mockFolder;
    const dialog = await import('@tauri-apps/plugin-dialog');
    return dialog.open({ directory: true, multiple: false });
  },

  async listenPipelineEvents(onEvent) {
    if (!hasTauri()) return () => {};
    const eventApi = await import('@tauri-apps/api/event');
    const unlistenProgress = await eventApi.listen('pipeline-progress', (event) => onEvent(event.payload));
    const unlistenCompleted = await eventApi.listen('pipeline-completed', (event) => onEvent({ ...event.payload, type: 'completed' }));
    const unlistenFailed = await eventApi.listen('pipeline-failed', (event) => onEvent({ ...event.payload, type: 'failed' }));
    const unlistenCancelled = await eventApi.listen('pipeline-cancelled', (event) => onEvent({ ...event.payload, type: 'cancelled' }));
    return () => {
      unlistenProgress();
      unlistenCompleted();
      unlistenFailed();
      unlistenCancelled();
    };
  },
  async startPipeline(folder) {
    if (!hasTauri()) return { taskId: 'mock-task' };
    return invoke('start_pipeline', { folder });
  },
  async cancelPipeline(taskId) {
    if (!hasTauri()) return;
    return invoke('cancel_pipeline', { taskId });
  },
  async loadReviewSummary(folder) {
    if (!hasTauri()) return mockSummary;
    return invoke('load_review_summary', { folder });
  },
  async loadReviewSets(folder) {
    if (!hasTauri()) return mockReviewSets;
    return invoke('load_review_sets', { folder });
  },
  async readImageDataUrl(folder, artifactPath) {
    if (!hasTauri()) return resolveAssetPath(folder, artifactPath);
    return invoke('read_image_data_url', { folder, artifactPath });
  },
  async appendDecision(folder, decision) {
    if (!hasTauri()) {
      console.info('[mock decision]', folder, decision);
      return;
    }
    return invoke('append_decision', { folder, decision });
  },
  async loadDecisions(folder) {
    if (!hasTauri()) return mockDecisions;
    return invoke('load_decisions', { folder });
  },
  async loadReviewProgress(folder) {
    if (!hasTauri()) return mockProgress;
    return invoke('load_review_progress', { folder });
  },
  async saveReviewProgress(folder, progress) {
    if (!hasTauri()) {
      mockProgress.completed_review_set_ids = progress.completed_review_set_ids || [];
      return;
    }
    return invoke('save_review_progress', { folder, progress });
  },
  async appendPreferenceEvent(folder, event) {
    if (!hasTauri()) {
      console.info('[mock preference]', folder, event);
      return;
    }
    return invoke('append_preference_event', { folder, event });
  },
  async dryRunStage(folder) {
    if (!hasTauri()) return { schema_version: '1.0', plan_id: 'mock-plan', move_count: 2, sidecar_count: 1, operations: [], issues: [] };
    return invoke('dry_run_stage', { folder });
  },
  async executeStage(folder, planId) {
    if (!hasTauri()) return { schema_version: '1.0', operation_batch_id: 'mock-batch', moved_count: 3, failed_count: 0, failures: [] };
    return invoke('execute_stage', { folder, planId });
  },
  async undoStage(folder, operationBatchId) {
    if (!hasTauri()) return { schema_version: '1.0', operation_batch_id: operationBatchId, restored_count: 3, failed_count: 0, failures: [] };
    return invoke('undo_stage', { folder, operationBatchId });
  },
};
