from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from cullary.analyzers.embedding import EmbeddingAnalyzer
from cullary.analyzers.face import FaceAnalyzer
from cullary.analyzers.hash import compute_hashes
from cullary.analyzers.image_metrics import compute_image_metrics
from cullary.analyzers.iqa import IqaAnalyzer
from cullary.analyzers.media import create_thumb, extract_metadata, extract_preview
from cullary.analyzers.person_mask import PersonMaskAnalyzer
from cullary.constants import ANALYZER_VERSIONS, DEPENDENCIES, IGNORED_NAMES, PIPELINE_STAGES, SCHEMA_VERSION, SUPPORTED_EXTENSIONS
from cullary.domain import AnalyzerStatus, PhotoRecord
from cullary.features import default_score_features
from cullary.state import TaskState
from cullary.utils import (
    cache_relative,
    config_hash,
    ensure_tools,
    now_iso,
    read_json,
    read_manifest,
    relative_to_folder,
    sanitize_display_id,
    source_id_for,
    write_json,
    write_jsonl,
)


PARALLEL_EXECUTOR_BY_STAGE = {
    "metadata": "thread",
    "preview": "thread",
    "thumb": "process",
    "hash": "process",
    "image_metrics": "process",
}


def execute_stage_worker(stage: str, rec: PhotoRecord, config: dict[str, Any], tools: dict[str, str | None], folder: Path) -> tuple[str, AnalyzerStatus, dict[str, Any] | None]:
    started_at = now_iso()
    start = time.perf_counter()
    try:
        payload, error, output_path = execute_stage_payload_worker(stage, rec, config, tools, folder)
        status_name = "failed" if error else "success"
    except Exception as exc:
        payload, error, output_path = None, f"{type(exc).__name__}: {exc}", None
        status_name = "failed"
    status = AnalyzerStatus(
        status_name,
        ANALYZER_VERSIONS[stage],
        config_hash(config, stage),
        int((time.perf_counter() - start) * 1000),
        started_at,
        now_iso(),
        error,
        cache_relative(Path(output_path), folder) if output_path else None,
    )
    return rec.source_id, status, payload


def execute_stage_payload_worker(stage: str, rec: PhotoRecord, config: dict[str, Any], tools: dict[str, str | None], folder: Path) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if stage == "metadata":
        if not tools.get("exiftool"):
            return None, "exiftool is required but was not found", None
        payload = extract_metadata(rec.source_path, rec.metadata_raw_path, tools.get("exiftool"))
        payload["raw_path"] = cache_relative(rec.metadata_raw_path, folder)
        return payload, None, str(rec.analysis_path)
    if stage == "preview":
        payload, error = extract_preview(rec.source_path, rec.preview_path, int(config["preview"]["long_edge"]), tools.get("sips"), tools.get("exiftool"))
        if payload and rec.preview_path.exists():
            payload["preview_path"] = cache_relative(rec.preview_path, folder)
        return payload, error, str(rec.preview_path) if not error else None
    if stage == "thumb":
        payload = create_thumb(rec.preview_path, rec.thumb_path, int(config["thumb"]["long_edge"]))
        payload["thumb_path"] = cache_relative(rec.thumb_path, folder)
        return payload, None, str(rec.thumb_path)
    if stage == "hash":
        return compute_hashes(rec.preview_path), None, str(rec.analysis_path)
    if stage == "image_metrics":
        metrics = compute_image_metrics(rec.preview_path, int(config["image_metrics"]["max_side"]))
        if metrics.get("status") != "success":
            return None, metrics.get("error", "image metrics failed"), None
        return metrics["image_metrics"], None, str(rec.analysis_path)
    return None, f"unsupported parallel stage: {stage}", None


class PreprocessPipeline:
    def __init__(
        self,
        folder: Path,
        config: dict[str, Any],
        *,
        force: bool = False,
        limit: int | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.folder = folder.resolve()
        self.config = config
        self.force = force
        self.limit = limit
        self.cache_dir = self.folder / config.get("cache", {}).get("dir_name", ".cullary")
        self.models_dir = Path(config.get("models", {}).get("model_dir", "~/.cullary/models")).expanduser().resolve()
        self.manifest_path = self.cache_dir / "manifest.jsonl"
        self.summary_path = self.cache_dir / "run_summary.json"
        self.task_state_path = self.cache_dir / "task_state.json"
        self.started_perf = time.perf_counter()
        self.tools = ensure_tools()
        self.records: list[PhotoRecord] = []
        self.existing_manifest = read_manifest(self.manifest_path)
        self.task: TaskState | None = None
        self.embedding_analyzer = EmbeddingAnalyzer(self.models_dir, self.config.get("embedding", {}))
        self.face_analyzer = FaceAnalyzer(self.models_dir, self.config.get("face", {}))
        self.person_mask_analyzer = PersonMaskAnalyzer(self.models_dir, self.config.get("person_mask", {}))
        self.iqa_analyzer = IqaAnalyzer(self.models_dir, self.config.get("iqa", {}))
        self.progress = progress
        self.pipeline_config = self.config.get("pipeline", {})

    def run(self) -> dict[str, Any]:
        self.ensure_cache_dirs()
        write_json(self.cache_dir / "config.snapshot.json", self.config)
        self.emit("task_start", folder=str(self.folder), cache_dir=str(self.cache_dir))
        self.records = self.scan_records()
        self.emit("scan_done", total=len(self.records), ignored=getattr(self, "ignored", {}))
        self.task = TaskState(self.make_task_id(), self.folder, self.cache_dir, self.task_state_path, len(self.records))
        self.task.persist()
        self.mark_scan_done()
        for stage in [s for s in PIPELINE_STAGES if s != "scan"]:
            self.run_stage(stage)
            self.write_manifest()
        summary = self.build_summary()
        final_status = "success" if not summary["failures"] else "partial_success"
        if self.task:
            self.task.status = final_status
            self.task.current_stage = "summary"
            self.task.totals["completed"] = sum(1 for r in self.records if self.overall_status(r) == "success")
            self.task.totals["failed"] = sum(1 for r in self.records if self.overall_status(r) in {"failed", "partial"})
            self.task.totals["skipped"] = max((self.task.stages[stage].skipped for stage in self.stages_without_scan()), default=0)
            self.task.persist()
        write_json(self.summary_path, summary)
        self.emit("task_done", status=summary["status"], total_photos=len(self.records), duration_ms=summary["duration_ms"])
        return summary

    def emit(self, event_type: str, **payload: Any) -> None:
        if self.progress:
            self.progress({"type": event_type, **payload})

    def ensure_cache_dirs(self) -> None:
        for name in ["previews", "thumbs", "analysis", "embeddings", "foreground_embeddings", "background_embeddings", "masks", "foregrounds", "backgrounds", "logs"]:
            (self.cache_dir / name).mkdir(parents=True, exist_ok=True)

    def make_task_id(self) -> str:
        return f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-{self.folder.name}"

    def scan_files(self) -> tuple[list[Path], dict[str, int]]:
        files: list[Path] = []
        ignored: dict[str, int] = {}
        ignored_dirs = {self.cache_dir.name, ".cullary", ".cullary_cache", "__MACOSX"}
        for root, dirs, names in __import__("os").walk(self.folder):
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".cullary")]
            for name in names:
                path = Path(root) / name
                suffix = path.suffix.lower()
                if name in IGNORED_NAMES or suffix == ".crdownload":
                    ignored[suffix or name] = ignored.get(suffix or name, 0) + 1
                    continue
                if suffix in SUPPORTED_EXTENSIONS:
                    files.append(path)
                else:
                    ignored[suffix or "<none>"] = ignored.get(suffix or "<none>", 0) + 1
        files = sorted(files, key=lambda p: str(p.relative_to(self.folder)))
        if self.limit is not None:
            files = files[: self.limit]
        self.ignored = ignored
        return files, ignored

    def scan_records(self) -> list[PhotoRecord]:
        files, _ = self.scan_files()
        base_counts: dict[str, int] = {}
        for path in files:
            base = sanitize_display_id(path)
            base_counts[base] = base_counts.get(base, 0) + 1
        records: list[PhotoRecord] = []
        for source in files:
            stat = source.stat()
            source_id = source_id_for(source, self.folder)
            base_display_id = sanitize_display_id(source)
            display_id = f"{base_display_id}_{source_id[:8]}" if base_counts.get(base_display_id, 0) > 1 else base_display_id
            existing = self.existing_manifest.get(source_id, {})
            analysis_dir = self.cache_dir / "analysis" / display_id
            existing_analysis = read_json(analysis_dir / "analysis.json") or {}
            existing_source = existing.get("source") or existing_analysis.get("source", {})
            source_changed = not (existing_source.get("size") == stat.st_size and existing_source.get("mtime_ns") == stat.st_mtime_ns)
            records.append(PhotoRecord(
                source_id=source_id,
                display_id=display_id,
                source_path=source,
                relative_path=relative_to_folder(source, self.folder),
                file_name=source.name,
                extension=source.suffix.lower(),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                analysis_dir=analysis_dir,
                analysis_path=analysis_dir / "analysis.json",
                preview_path=self.cache_dir / "previews" / f"{display_id}.jpg",
                thumb_path=self.cache_dir / "thumbs" / f"{display_id}.jpg",
                embedding_path=self.cache_dir / "embeddings" / f"{display_id}.npy",
                foreground_embedding_path=self.cache_dir / "foreground_embeddings" / f"{display_id}.npy",
                background_embedding_path=self.cache_dir / "background_embeddings" / f"{display_id}.npy",
                person_mask_path=self.cache_dir / "masks" / f"{display_id}__person.png",
                person_enhanced_mask_path=self.cache_dir / "masks" / f"{display_id}__person_enhanced.png",
                foreground_path=self.cache_dir / "foregrounds" / f"{display_id}.jpg",
                background_path=self.cache_dir / "backgrounds" / f"{display_id}.jpg",
                metadata_raw_path=analysis_dir / "metadata.raw.json",
                source_changed=source_changed,
                analysis=self.load_or_init_analysis(source_id, display_id, source, stat, analysis_dir, existing_analysis),
            ))
        return records

    def load_or_init_analysis(self, source_id: str, display_id: str, source: Path, stat: Any, analysis_dir: Path, existing: dict[str, Any] | None = None) -> dict[str, Any]:
        existing = existing or read_json(analysis_dir / "analysis.json") or {}
        return {
            "schema_version": SCHEMA_VERSION,
            "source_id": source_id,
            "display_id": display_id,
            "source": {"path": str(source), "relative_path": relative_to_folder(source, self.folder), "file_name": source.name, "extension": source.suffix.lower(), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns},
            "assets": existing.get("assets", {}),
            "metadata": existing.get("metadata", {}),
            "hash": existing.get("hash", {}),
            "image_metrics": existing.get("image_metrics", {}),
            "embedding": existing.get("embedding", {}),
            "foreground_embedding": existing.get("foreground_embedding"),
            "background_embedding": existing.get("background_embedding"),
            "person_mask": existing.get("person_mask", {}),
            "face_metrics": existing.get("face_metrics", {}),
            "iqa_metrics": existing.get("iqa_metrics", {}),
            "score_features": existing.get("score_features", default_score_features()),
            "analyzer_status": existing.get("analyzer_status", {}),
        }

    def mark_scan_done(self) -> None:
        if not self.task:
            return
        runtime = self.task.stages["scan"]
        runtime.status = "success"
        runtime.done = runtime.total = len(self.records)
        runtime.finished_at = now_iso()
        self.write_manifest()
        self.task.persist()

    def run_stage(self, stage: str) -> None:
        if stage == "embedding":
            self.run_embedding_stage(stage)
            return
        if stage == "iqa":
            self.run_iqa_stage(stage)
            return
        if self.stage_workers(stage) > 1 and stage in PARALLEL_EXECUTOR_BY_STAGE:
            self.run_parallel_stage(stage)
            return
        self.run_serial_stage(stage)

    def begin_stage(self, stage: str) -> tuple[Any, float, int]:
        assert self.task is not None
        runtime = self.task.stages[stage]
        runtime.total = len(self.records)
        runtime.done = runtime.failed = runtime.skipped = 0
        stage_start = time.perf_counter()
        self.task.set_stage(stage, "running")
        self.task.persist()
        self.emit("stage_start", stage=stage, total=len(self.records))
        progress_every = max(1, min(10, len(self.records) // 10 or 1))
        return runtime, stage_start, progress_every

    def finish_stage(self, stage: str, stage_start: float) -> None:
        assert self.task is not None
        runtime = self.task.stages[stage]
        runtime.duration_ms = int((time.perf_counter() - stage_start) * 1000)
        self.task.finish_stage(stage)
        self.task.persist()
        self.emit("stage_done", stage=stage, skipped=runtime.skipped, failed=runtime.failed, duration_ms=runtime.duration_ms, workers=self.stage_workers(stage))

    def record_progress(self, stage: str, progress_every: int) -> None:
        assert self.task is not None
        runtime = self.task.stages[stage]
        self.task.persist()
        if runtime.done == 1 or runtime.done == runtime.total or runtime.done % progress_every == 0:
            self.emit("stage_progress", stage=stage, done=runtime.done, total=runtime.total, skipped=runtime.skipped, failed=runtime.failed)

    def run_serial_stage(self, stage: str) -> None:
        assert self.task is not None
        runtime, stage_start, progress_every = self.begin_stage(stage)
        for rec in self.records:
            touched = False
            if not self.dependencies_ready(stage, rec):
                self.set_status(rec, stage, self.make_status(stage, "skipped", 0, "dependency unavailable", None))
                runtime.skipped += 1; runtime.done += 1; touched = True
            elif self.should_skip(rec, stage):
                runtime.skipped += 1; runtime.done += 1
            else:
                status, payload = self.execute_stage(stage, rec)
                self.apply_payload(rec, stage, payload)
                self.set_status(rec, stage, status)
                if status.status == "success":
                    rec.changed_stages.add(stage)
                if status.status == "skipped":
                    runtime.skipped += 1
                if status.status == "failed":
                    runtime.failed += 1
                    self.task.errors.append({"source": str(rec.source_path), "stage": stage, "error": status.error_message})
                runtime.done += 1; touched = True
            if touched:
                self.write_analysis(rec)
            self.record_progress(stage, progress_every)
        self.finish_stage(stage, stage_start)

    def run_parallel_stage(self, stage: str) -> None:
        assert self.task is not None
        runtime, stage_start, progress_every = self.begin_stage(stage)
        pending: list[PhotoRecord] = []
        for rec in self.records:
            if not self.dependencies_ready(stage, rec):
                self.set_status(rec, stage, self.make_status(stage, "skipped", 0, "dependency unavailable", None))
                runtime.skipped += 1; runtime.done += 1
                self.write_analysis(rec)
                self.record_progress(stage, progress_every)
            elif self.should_skip(rec, stage):
                runtime.skipped += 1; runtime.done += 1
                self.record_progress(stage, progress_every)
            else:
                pending.append(rec)
        rec_by_source_id = {rec.source_id: rec for rec in pending}
        executor_cls = ThreadPoolExecutor if PARALLEL_EXECUTOR_BY_STAGE[stage] == "thread" else ProcessPoolExecutor
        workers = self.stage_workers(stage)
        if pending:
            try:
                executor = executor_cls(max_workers=workers)
            except (OSError, PermissionError) as exc:
                self.emit("stage_warning", stage=stage, message=f"process executor unavailable, falling back to threads: {type(exc).__name__}: {exc}")
                executor = ThreadPoolExecutor(max_workers=workers)
            with executor:
                futures = {executor.submit(execute_stage_worker, stage, rec, self.config, self.tools, self.folder): rec for rec in pending}
                for future in as_completed(futures):
                    rec = futures[future]
                    try:
                        source_id, status, payload = future.result()
                        rec = rec_by_source_id[source_id]
                    except Exception as exc:
                        status = self.make_status(stage, "failed", 0, f"{type(exc).__name__}: {exc}", None)
                        payload = None
                    self.apply_stage_result(rec, stage, status, payload)
                    runtime.done += 1
                    self.write_analysis(rec)
                    self.record_progress(stage, progress_every)
        self.finish_stage(stage, stage_start)

    def run_embedding_stage(self, stage: str) -> None:
        assert self.task is not None
        runtime, stage_start, progress_every = self.begin_stage(stage)
        batch: list[PhotoRecord] = []
        batch_size = self.embedding_analyzer.batch_size()
        for rec in self.records:
            if not self.dependencies_ready(stage, rec):
                self.set_status(rec, stage, self.make_status(stage, "skipped", 0, "dependency unavailable", None))
                runtime.skipped += 1; runtime.done += 1
                self.write_analysis(rec)
                self.record_progress(stage, progress_every)
            elif self.should_skip(rec, stage):
                runtime.skipped += 1; runtime.done += 1
                self.record_progress(stage, progress_every)
            else:
                batch.append(rec)
                if len(batch) >= batch_size:
                    self.process_embedding_batch(stage, batch, progress_every)
                    batch = []
        if batch:
            self.process_embedding_batch(stage, batch, progress_every)
        self.finish_stage(stage, stage_start)

    def process_embedding_batch(self, stage: str, records: list[PhotoRecord], progress_every: int) -> None:
        assert self.task is not None
        from PIL import Image

        runtime = self.task.stages[stage]
        started_at = now_iso()
        start = time.perf_counter()
        items: list[tuple[Any, Path, PhotoRecord, str]] = []
        load_failures: dict[str, str] = {}
        for rec in records:
            try:
                with Image.open(rec.preview_path) as image:
                    items.append((image.convert("RGB"), rec.embedding_path, rec, "embedding"))
                person_mask = rec.analysis.get("person_mask") or {}
                if person_mask.get("status") == "success":
                    if rec.foreground_path.exists():
                        with Image.open(rec.foreground_path) as image:
                            items.append((image.convert("RGB"), rec.foreground_embedding_path, rec, "foreground_embedding"))
                    if rec.background_path.exists():
                        with Image.open(rec.background_path) as image:
                            items.append((image.convert("RGB"), rec.background_embedding_path, rec, "background_embedding"))
            except Exception as exc:
                load_failures[rec.source_id] = f"{type(exc).__name__}: {exc}"
        try:
            batch_results = self.embedding_analyzer.analyze_batch([(image, path) for image, path, _, _ in items])
        except Exception as exc:
            batch_results = [(None, f"{type(exc).__name__}: {exc}") for _ in items]
        result_by_source_id: dict[str, dict[str, tuple[dict[str, Any] | None, str | None, Path]]] = {}
        for (_, path, rec, kind), result in zip(items, batch_results):
            result_by_source_id.setdefault(rec.source_id, {})[kind] = (result[0], result[1], path)
        for rec in records:
            kinds = result_by_source_id.get(rec.source_id, {})
            global_payload, global_error, global_path = kinds.get("embedding", (None, load_failures.get(rec.source_id, "embedding batch did not return a result"), rec.embedding_path))
            if global_payload:
                global_payload["vector_path"] = cache_relative(global_path, self.folder)
                global_payload["embedding_role"] = "global"
            for role, target_key in [("foreground_embedding", "foreground"), ("background_embedding", "background")]:
                payload, error, path = kinds.get(role, (None, None, getattr(rec, f"{target_key}_embedding_path")))
                if payload and not error:
                    payload["vector_path"] = cache_relative(path, self.folder)
                    payload["embedding_role"] = target_key
                    payload["preview_source"] = f"{target_key}_path"
                    rec.analysis[role] = payload
                elif (rec.analysis.get("person_mask") or {}).get("status") == "success":
                    rec.analysis[role] = {"status": "failed", "error_message": error or "not generated"}
                else:
                    rec.analysis[role] = None
            output_path = str(rec.embedding_path) if not global_error else None
            status = AnalyzerStatus(
                "failed" if global_error else "success",
                ANALYZER_VERSIONS[stage],
                config_hash(self.config, stage),
                int((time.perf_counter() - start) * 1000),
                started_at,
                now_iso(),
                global_error,
                cache_relative(Path(output_path), self.folder) if output_path else None,
            )
            self.apply_stage_result(rec, stage, status, global_payload)
            runtime.done += 1
            self.write_analysis(rec)
            self.record_progress(stage, progress_every)

    def run_iqa_stage(self, stage: str) -> None:
        assert self.task is not None
        runtime, stage_start, progress_every = self.begin_stage(stage)
        batch: list[PhotoRecord] = []
        batch_size = self.iqa_analyzer.batch_size()
        for rec in self.records:
            if not self.dependencies_ready(stage, rec):
                self.set_status(rec, stage, self.make_status(stage, "skipped", 0, "dependency unavailable", None))
                runtime.skipped += 1; runtime.done += 1
                self.write_analysis(rec)
                self.record_progress(stage, progress_every)
            elif self.should_skip(rec, stage):
                runtime.skipped += 1; runtime.done += 1
                self.record_progress(stage, progress_every)
            else:
                batch.append(rec)
                if len(batch) >= batch_size:
                    self.process_iqa_batch(stage, batch, progress_every)
                    batch = []
        if batch:
            self.process_iqa_batch(stage, batch, progress_every)
        self.finish_stage(stage, stage_start)

    def process_iqa_batch(self, stage: str, records: list[PhotoRecord], progress_every: int) -> None:
        assert self.task is not None
        runtime = self.task.stages[stage]
        started_at = now_iso()
        start = time.perf_counter()
        metric_name = self.config.get("iqa", {}).get("metric", "piqe")
        items = [(rec.preview_path, rec.analysis_dir / f"iqa_{metric_name}_input.jpg") for rec in records]
        try:
            batch_results = self.iqa_analyzer.analyze_batch(items)
        except Exception as exc:
            batch_results = [(None, f"{type(exc).__name__}: {exc}") for _ in records]
        for rec, input_path, (payload, error) in zip(records, [item[1] for item in items], batch_results):
            if payload:
                payload.setdefault("input", {})["path"] = cache_relative(input_path, self.folder)
            status = AnalyzerStatus(
                "failed" if error else "success",
                ANALYZER_VERSIONS[stage],
                config_hash(self.config, stage),
                int((time.perf_counter() - start) * 1000),
                started_at,
                now_iso(),
                error,
                cache_relative(rec.analysis_path, self.folder) if not error else None,
            )
            self.apply_stage_result(rec, stage, status, payload)
            runtime.done += 1
            self.write_analysis(rec)
            self.record_progress(stage, progress_every)

    def stage_workers(self, stage: str) -> int:
        stage_workers = self.pipeline_config.get("stage_workers", {})
        value = stage_workers.get(stage, self.pipeline_config.get("default_workers", 1))
        return max(1, int(value))

    def apply_stage_result(self, rec: PhotoRecord, stage: str, status: AnalyzerStatus, payload: dict[str, Any] | None) -> None:
        assert self.task is not None
        self.apply_payload(rec, stage, payload)
        self.set_status(rec, stage, status)
        if status.status == "success":
            rec.changed_stages.add(stage)
        if status.status == "failed":
            self.task.stages[stage].failed += 1
            self.task.errors.append({"source": str(rec.source_path), "stage": stage, "error": status.error_message})

    def dependencies_ready(self, stage: str, rec: PhotoRecord) -> bool:
        for dep in DEPENDENCIES.get(stage, []):
            if rec.analysis.get("analyzer_status", {}).get(dep, {}).get("status") not in {"success", "skipped"}:
                return False
            if dep == "preview" and not rec.preview_path.exists():
                return False
        return True

    def should_skip(self, rec: PhotoRecord, stage: str) -> bool:
        if any(dep in rec.changed_stages for dep in DEPENDENCIES.get(stage, [])):
            return False
        if self.force or rec.source_changed:
            return False
        status = rec.analysis.get("analyzer_status", {}).get(stage, {})
        if status.get("status") != "success" or status.get("version") != ANALYZER_VERSIONS[stage] or status.get("config_hash") != config_hash(self.config, stage):
            return False
        output = status.get("output_path")
        return not (output and not (self.folder / output).exists() and not Path(output).exists())

    def execute_stage(self, stage: str, rec: PhotoRecord) -> tuple[AnalyzerStatus, dict[str, Any] | None]:
        started_at = now_iso(); start = time.perf_counter()
        try:
            payload, error, output_path = self._execute_stage_payload(stage, rec)
            if stage == "person_mask" and payload and payload.get("reason") == "no_face_detected":
                status_name = "skipped"
                error = payload.get("reason")
            else:
                status_name = "failed" if error else "success"
        except Exception as exc:
            payload, error, output_path = None, f"{type(exc).__name__}: {exc}", None
            status_name = "failed"
        status = AnalyzerStatus(status_name, ANALYZER_VERSIONS[stage], config_hash(self.config, stage), int((time.perf_counter() - start) * 1000), started_at, now_iso(), error, cache_relative(Path(output_path), self.folder) if output_path else None)
        return status, payload

    def _execute_stage_payload(self, stage: str, rec: PhotoRecord) -> tuple[dict[str, Any] | None, str | None, str | None]:
        if stage == "metadata":
            if not self.tools.get("exiftool"):
                return None, "exiftool is required but was not found", None
            payload = extract_metadata(rec.source_path, rec.metadata_raw_path, self.tools.get("exiftool"))
            payload["raw_path"] = cache_relative(rec.metadata_raw_path, self.folder)
            return payload, None, str(rec.analysis_path)
        if stage == "preview":
            payload, error = extract_preview(rec.source_path, rec.preview_path, int(self.config["preview"]["long_edge"]), self.tools.get("sips"), self.tools.get("exiftool"))
            if payload and rec.preview_path.exists():
                payload["preview_path"] = cache_relative(rec.preview_path, self.folder)
            return payload, error, str(rec.preview_path) if not error else None
        if stage == "thumb":
            payload = create_thumb(rec.preview_path, rec.thumb_path, int(self.config["thumb"]["long_edge"]))
            payload["thumb_path"] = cache_relative(rec.thumb_path, self.folder)
            return payload, None, str(rec.thumb_path)
        if stage == "hash":
            return compute_hashes(rec.preview_path), None, str(rec.analysis_path)
        if stage == "image_metrics":
            metrics = compute_image_metrics(rec.preview_path, int(self.config["image_metrics"]["max_side"]))
            if metrics.get("status") != "success":
                return None, metrics.get("error", "image metrics failed"), None
            return metrics["image_metrics"], None, str(rec.analysis_path)
        if stage == "embedding":
            payload, error = self.embedding_analyzer.analyze(rec.preview_path, rec.embedding_path)
            if payload:
                payload["vector_path"] = cache_relative(rec.embedding_path, self.folder)
            return payload, error, str(rec.embedding_path) if not error else None
        if stage == "face":
            payload, error = self.face_analyzer.analyze(rec.preview_path)
            return payload, error, str(rec.analysis_path) if not error else None
        if stage == "person_mask":
            payload, error, output_path = self.person_mask_analyzer.analyze(
                rec.preview_path,
                rec.analysis.get("face_metrics", {}),
                mask_path=rec.person_mask_path,
                enhanced_mask_path=rec.person_enhanced_mask_path,
                background_path=rec.background_path,
                foreground_path=rec.foreground_path,
            )
            if payload:
                status_override = payload.pop("__status", None)
                reason = payload.get("reason")
                if status_override == "skipped":
                    return payload, None, None
                for key in ["mask_path", "enhanced_mask_path", "background_fill_path", "foreground_path"]:
                    if key in payload:
                        payload[key] = cache_relative(Path(payload[key]), self.folder)
            return payload, error, output_path if not error else None
        if stage == "iqa":
            metric_name = self.config.get("iqa", {}).get("metric", "piqe")
            input_path = rec.analysis_dir / f"iqa_{metric_name}_input.jpg"
            payload, error = self.iqa_analyzer.analyze(rec.preview_path, input_path)
            if payload:
                payload.setdefault("input", {})["path"] = cache_relative(input_path, self.folder)
            return payload, error, str(rec.analysis_path) if not error else None
        return None, f"unknown stage: {stage}", None

    def make_status(self, stage: str, status: str, duration_ms: int, error: str | None, output: str | None) -> AnalyzerStatus:
        ts = now_iso()
        return AnalyzerStatus(status, ANALYZER_VERSIONS[stage], config_hash(self.config, stage), duration_ms, ts, ts, error, output)

    def set_status(self, rec: PhotoRecord, stage: str, status: AnalyzerStatus) -> None:
        rec.analysis.setdefault("analyzer_status", {})[stage] = status.to_dict()

    def apply_payload(self, rec: PhotoRecord, stage: str, payload: dict[str, Any] | None) -> None:
        if payload is None:
            return
        if stage == "metadata": rec.analysis["metadata"] = payload
        elif stage in {"preview", "thumb"}: rec.analysis["assets"] = {**rec.analysis.get("assets", {}), **payload}
        elif stage == "hash": rec.analysis["hash"] = payload
        elif stage == "image_metrics": rec.analysis["image_metrics"] = payload
        elif stage == "embedding": rec.analysis["embedding"] = payload
        elif stage == "face": rec.analysis["face_metrics"] = payload
        elif stage == "person_mask": rec.analysis["person_mask"] = payload
        elif stage == "iqa": rec.analysis["iqa_metrics"] = payload

    def write_analysis(self, rec: PhotoRecord) -> None:
        person_mask = rec.analysis.get("person_mask") or {}
        if person_mask.get("status") == "success":
            rec.analysis.setdefault("image_metrics", {}).setdefault("foreground", {})
            rec.analysis["image_metrics"]["foreground"].update({
                "foreground_area_ratio": person_mask.get("foreground_area_ratio"),
                "foreground_enhanced_area_ratio": person_mask.get("foreground_enhanced_area_ratio"),
                "source": "person_mask",
            })
        rec.analysis["score_features"] = rec.analysis.get("score_features") or default_score_features()
        write_json(rec.analysis_path, rec.analysis)

    def write_manifest(self) -> None:
        write_jsonl(self.manifest_path, [self.manifest_record(rec) for rec in self.records])

    def manifest_record(self, rec: PhotoRecord) -> dict[str, Any]:
        statuses = rec.analysis.get("analyzer_status", {})
        status_map = {stage: statuses.get(stage, {}).get("status", "pending") for stage in PIPELINE_STAGES if stage != "scan"}
        metrics = rec.analysis.get("image_metrics", {})
        face = rec.analysis.get("face_metrics", {})
        person_mask = rec.analysis.get("person_mask", {})
        exposure = metrics.get("exposure", {}) if isinstance(metrics, dict) else {}
        warnings = []
        if exposure.get("shadow_clip_ratio", 0) > 0.05: warnings.append("shadow_clip")
        if exposure.get("highlight_clip_ratio", 0) > 0.03: warnings.append("highlight_clip")
        return {
            "schema_version": SCHEMA_VERSION,
            "source_id": rec.source_id,
            "display_id": rec.display_id,
            "source": rec.analysis["source"],
            "assets": rec.analysis.get("assets", {}),
            "analysis_path": cache_relative(rec.analysis_path, self.folder),
            "status": {"overall": self.overall_status(rec), **status_map},
            "ui_summary": {"orientation": metrics.get("composition", {}).get("orientation"), "face_count": face.get("face_count"), "foreground_area_ratio": person_mask.get("foreground_area_ratio"), "quality_label": "normal", "warning_flags": warnings},
        }

    def overall_status(self, rec: PhotoRecord) -> str:
        statuses = rec.analysis.get("analyzer_status", {})
        values = [statuses.get(stage, {}).get("status", "pending") for stage in PIPELINE_STAGES if stage != "scan"]
        if values and all(v in {"success", "skipped"} for v in values): return "success"
        if any(v == "failed" for v in values): return "partial"
        return "pending"

    def stages_without_scan(self) -> list[str]:
        return [stage for stage in PIPELINE_STAGES if stage != "scan"]

    def build_summary(self) -> dict[str, Any]:
        analyzer_counts: dict[str, dict[str, int]] = {}
        failures: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for rec in self.records:
            for stage, status in rec.analysis.get("analyzer_status", {}).items():
                name = status.get("status", "unknown")
                analyzer_counts.setdefault(stage, {})[name] = analyzer_counts.setdefault(stage, {}).get(name, 0) + 1
                if name == "failed": failures.append({"source": str(rec.source_path), "stage": stage, "error": status.get("error_message")})
                if name == "skipped": skipped.append({"source": str(rec.source_path), "stage": stage, "reason": status.get("error_message")})
        by_extension: dict[str, int] = {}
        for rec in self.records:
            by_extension[rec.extension] = by_extension.get(rec.extension, 0) + 1
        duration_ms = int((time.perf_counter() - self.started_perf) * 1000)
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "success" if not failures else "partial_success",
            "duration_ms": duration_ms,
            "per_100_estimate_ms": int(duration_ms / max(len(self.records), 1) * 100) if self.records else 0,
            "stage_runtime": self.task.to_dict()["stages"] if self.task else {},
            "folder": str(self.folder),
            "cache_dir": str(self.cache_dir),
            "models_dir": str(self.models_dir),
            "python": sys.executable,
            "tools": self.tools,
            "total_photos": len(self.records),
            "by_extension": by_extension,
            "ignored": getattr(self, "ignored", {}),
            "analyzer_counts": analyzer_counts,
            "failures": failures,
            "skipped": skipped[:100],
            "task_state_path": str(self.task_state_path),
            "manifest_path": str(self.manifest_path),
        }
