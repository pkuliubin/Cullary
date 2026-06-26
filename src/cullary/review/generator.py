from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

from cullary.utils import config_hash, now_iso, read_json, stable_json, write_json, write_jsonl

SCHEMA_VERSION = "1.1"


@dataclass
class ReviewPhoto:
    manifest: dict[str, Any]
    analysis: dict[str, Any]
    embedding: np.ndarray
    foreground_embedding: np.ndarray | None
    background_embedding: np.ndarray | None
    foreground_area_ratio: float | None
    capture_time: datetime | None
    capture_time_raw: str | None
    score: dict[str, float]
    score_missing: list[str]
    badges: list[str]
    warnings: list[str]
    reason_summary_zh: list[str]
    weakness_summary_zh: list[str]

    @property
    def display_id(self) -> str:
        return str(self.manifest["display_id"])

    @property
    def source_id(self) -> str:
        return str(self.manifest["source_id"])


class ReviewSetGenerator:
    def __init__(self, folder: Path, config: dict[str, Any], progress: Callable[[dict[str, Any]], None] | None = None, *, force: bool = False) -> None:
        self.folder = folder.resolve()
        self.config = config
        self.review_config = config.get("review", {})
        self.cache_dir = self.folder / config.get("cache", {}).get("dir_name", ".cullary")
        self.manifest_path = self.cache_dir / "manifest.jsonl"
        self.review_sets_path = self.cache_dir / "review_sets.jsonl"
        self.review_summary_path = self.cache_dir / "review_summary.json"
        self.review_debug_path = self.cache_dir / "review_debug.json"
        self.progress = progress
        self.force = force
        self.started_perf = time.perf_counter()

    def run(self) -> dict[str, Any]:
        input_hash = self.input_hash()
        cached = self.cached_summary(input_hash)
        if cached is not None:
            self.emit("progress", stage="review_sets", done=cached.get("review_set_count", 0), total=cached.get("review_set_count", 0), message="Review sets cache hit")
            return cached
        self.emit("progress", stage="review_load", done=0, total=0, message="Loading Phase 1 artifacts")
        photos = self.load_photos()
        self.emit("progress", stage="review_load", done=len(photos), total=len(photos), message="Loaded Phase 1 artifacts")
        review_groups, cluster_debug = self.cluster_time_window_graph(photos)
        review_sets = self.build_review_sets(review_groups)
        write_jsonl(self.review_sets_path, review_sets)
        summary = self.build_summary(review_sets, photos, input_hash)
        write_json(self.review_summary_path, summary)
        write_json(self.review_debug_path, {
            "schema_version": SCHEMA_VERSION,
            **cluster_debug,
            "review_set_count": len(review_sets),
        })
        self.emit("progress", stage="review_sets", done=len(review_sets), total=len(review_sets), message="Review sets generated")
        return summary

    def emit(self, event_type: str, **payload: Any) -> None:
        if self.progress:
            self.progress({"type": event_type, **payload})

    def input_hash(self) -> str:
        h = hashlib.sha1()
        h.update(stable_json(self.review_config).encode("utf-8"))
        if self.manifest_path.exists():
            manifest_text = self.manifest_path.read_text(encoding="utf-8")
            h.update(manifest_text.encode("utf-8"))
            for line in manifest_text.splitlines():
                if not line.strip():
                    continue
                try:
                    record = __import__("json").loads(line)
                except Exception:
                    continue
                for rel in [record.get("analysis_path")]:
                    if rel:
                        path = self.resolve(rel)
                        if path.exists():
                            stat = path.stat(); h.update(f"{rel}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8"))
                            analysis = read_json(path) or {}
                            vector = analysis.get("embedding", {}).get("vector_path")
                            if vector:
                                vp = self.resolve(vector)
                                if vp.exists():
                                    vst = vp.stat(); h.update(f"{vector}:{vst.st_size}:{vst.st_mtime_ns}".encode("utf-8"))
        return h.hexdigest()[:20]

    def cached_summary(self, input_hash: str) -> dict[str, Any] | None:
        if self.force or not self.review_summary_path.exists() or not self.review_sets_path.exists():
            return None
        summary = read_json(self.review_summary_path)
        if (
            not summary
            or summary.get("status") != "success"
            or summary.get("schema_version") != SCHEMA_VERSION
            or summary.get("input_hash") != input_hash
        ):
            return None
        result = dict(summary)
        result["cache_hit"] = True
        return result

    def load_photos(self) -> list[ReviewPhoto]:
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"missing manifest: {self.manifest_path}")
        records = [__import__("json").loads(line) for line in self.manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        photos: list[ReviewPhoto] = []
        skipped: list[dict[str, str]] = []
        for record in records:
            display_id = str(record.get("display_id", "unknown"))
            if record.get("status", {}).get("overall") != "success":
                skipped.append({"display_id": display_id, "reason": "phase1_not_success"})
                continue
            analysis_rel = record.get("analysis_path")
            if not analysis_rel:
                skipped.append({"display_id": display_id, "reason": "missing_analysis_path"})
                continue
            analysis_path = self.resolve(analysis_rel)
            analysis = read_json(analysis_path)
            if not analysis:
                skipped.append({"display_id": display_id, "reason": "analysis_unreadable"})
                continue
            embedding_rel = analysis.get("embedding", {}).get("vector_path", "")
            embedding_path = self.resolve(embedding_rel)
            if not embedding_path.exists():
                skipped.append({"display_id": display_id, "reason": "embedding_missing"})
                continue
            try:
                embedding = load_normalized_vector(embedding_path)
            except Exception:
                skipped.append({"display_id": display_id, "reason": "embedding_unreadable"})
                continue
            foreground_embedding = load_optional_embedding(analysis.get("foreground_embedding"), self.folder)
            background_embedding = load_optional_embedding(analysis.get("background_embedding"), self.folder)
            person_mask = analysis.get("person_mask") or {}
            foreground_area_ratio = safe_float(person_mask.get("foreground_area_ratio"), None) if person_mask.get("status") == "success" else None
            capture_raw = self.capture_time_raw(analysis)
            capture_time = parse_capture_time(capture_raw) or datetime.fromtimestamp(float(analysis.get("source", {}).get("mtime_ns", 0)) / 1_000_000_000)
            score, missing = self.score_photo(analysis)
            badges, warnings, reasons, weaknesses = self.explain_photo(analysis, score, missing)
            photos.append(ReviewPhoto(record, analysis, embedding, foreground_embedding, background_embedding, foreground_area_ratio, capture_time, capture_raw, score, missing, badges, warnings, reasons, weaknesses))
        self.skipped_inputs = skipped
        photos.sort(key=lambda p: (p.capture_time or datetime.min, p.display_id))
        return photos

    def resolve(self, maybe_relative: str) -> Path:
        path = Path(maybe_relative)
        return path if path.is_absolute() else self.folder / path

    def capture_time_raw(self, analysis: dict[str, Any]) -> str | None:
        useful = analysis.get("metadata", {}).get("useful", {})
        return useful.get("date_time_original") or useful.get("create_date")

    def cluster_time_window_graph(self, photos: list[ReviewPhoto]) -> tuple[list[list[ReviewPhoto]], dict[str, Any]]:
        threshold = float(self.review_config.get("embedding_similarity_threshold", 0.86))
        near_threshold = float(self.review_config.get("near_duplicate_similarity_threshold", 0.93))
        candidate_window = int(self.review_config.get("candidate_time_window_seconds", 1800))
        neighbor_limit = int(self.review_config.get("candidate_neighbor_limit", 40))
        hard_gap = int(self.review_config.get("hard_time_gap_seconds", 3600))
        parent = list(range(len(photos)))
        edge_count = 0
        compared_pairs = 0
        hard_segment_count = 0

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        segment_start = 0
        while segment_start < len(photos):
            segment_end = segment_start + 1
            while segment_end < len(photos) and not self.is_hard_break(photos[segment_end - 1], photos[segment_end], hard_gap):
                segment_end += 1
            hard_segment_count += 1
            for local_i, i in enumerate(range(segment_start, segment_end)):
                checked = 0
                for j in range(i + 1, segment_end):
                    if checked >= neighbor_limit:
                        break
                    if time_distance_seconds(photos[i], photos[j]) > candidate_window:
                        break
                    checked += 1
                    compared_pairs += 1
                    decision = self.edge_decision(photos[i], photos[j], threshold)
                    if decision["edge"]:
                        union(i, j)
                        edge_count += 1
            segment_start = segment_end

        by_root: dict[int, list[ReviewPhoto]] = {}
        for idx, photo in enumerate(photos):
            by_root.setdefault(find(idx), []).append(photo)
        groups = sorted(by_root.values(), key=lambda g: (g[0].capture_time or datetime.min, g[0].display_id))
        debug = {
            "clustering_method": "time_window_candidate_graph_connected_components",
            "hard_segment_count": hard_segment_count,
            "candidate_time_window_seconds": candidate_window,
            "candidate_neighbor_limit": neighbor_limit,
            "hard_time_gap_seconds": hard_gap,
            "embedding_similarity_threshold": threshold,
            "near_duplicate_similarity_threshold": near_threshold,
            "compared_pairs": compared_pairs,
            "accepted_edges": edge_count,
            "group_sizes": [len(group) for group in groups],
        }
        return groups, debug

    def edge_decision(self, a: ReviewPhoto, b: ReviewPhoto, default_threshold: float) -> dict[str, Any]:
        global_sim = cosine(a.embedding, b.embedding)
        multi = self.review_config.get("multi_embedding", {})
        if not multi.get("enabled", True):
            return {"edge": global_sim >= default_threshold, "global_sim": global_sim, "combined_sim": global_sim}
        a_has = a.foreground_embedding is not None and a.background_embedding is not None
        b_has = b.foreground_embedding is not None and b.background_embedding is not None
        if a_has and b_has:
            foreground_sim = cosine(a.foreground_embedding, b.foreground_embedding)  # type: ignore[arg-type]
            background_sim = cosine(a.background_embedding, b.background_embedding)  # type: ignore[arg-type]
            combined = weighted([
                (global_sim, float(multi.get("global_weight", 0.45))),
                (background_sim, float(multi.get("background_weight", 0.30))),
                (foreground_sim, float(multi.get("foreground_weight", 0.25))),
            ])
            min_area = min(a.foreground_area_ratio or 0.0, b.foreground_area_ratio or 0.0)
            if background_sim < float(multi.get("background_veto_threshold", 0.60)):
                return {"edge": False, "global_sim": global_sim, "background_sim": background_sim, "foreground_sim": foreground_sim, "combined_sim": combined, "veto": "background"}
            if min_area >= float(multi.get("foreground_veto_min_area_ratio", 0.08)) and foreground_sim < float(multi.get("foreground_veto_threshold", 0.50)):
                return {"edge": False, "global_sim": global_sim, "background_sim": background_sim, "foreground_sim": foreground_sim, "combined_sim": combined, "veto": "foreground"}
            return {"edge": combined >= float(multi.get("combined_similarity_threshold", 0.84)), "global_sim": global_sim, "background_sim": background_sim, "foreground_sim": foreground_sim, "combined_sim": combined}
        if a_has != b_has:
            threshold = float(multi.get("mixed_foreground_global_threshold", 0.90))
            return {"edge": global_sim >= threshold, "global_sim": global_sim, "combined_sim": global_sim, "mixed_foreground": True}
        return {"edge": global_sim >= default_threshold, "global_sim": global_sim, "combined_sim": global_sim}

    def is_hard_break(self, previous: ReviewPhoto, current: ReviewPhoto, hard_gap: int) -> bool:
        if not previous.capture_time or not current.capture_time:
            return False
        if previous.capture_time.date() != current.capture_time.date():
            return True
        if time_distance_seconds(previous, current) > hard_gap:
            return True
        previous_meta = previous.analysis.get("metadata", {}).get("useful", {})
        current_meta = current.analysis.get("metadata", {}).get("useful", {})
        previous_camera = (previous_meta.get("make"), previous_meta.get("model"))
        current_camera = (current_meta.get("make"), current_meta.get("model"))
        if all(previous_camera) and all(current_camera) and previous_camera != current_camera:
            return True
        return False

    def build_review_sets(self, groups: list[list[ReviewPhoto]]) -> list[dict[str, Any]]:
        sets = []
        total = len(groups)
        for idx, group in enumerate(groups, start=1):
            ranked = self.rank_group(group)
            candidate_keep_count = self.keep_count(len(ranked))
            candidate_keepers = ranked[:candidate_keep_count]
            primary_keeper = candidate_keepers[0]
            alternate_keepers = candidate_keepers[1:]
            cover = primary_keeper
            photos_payload = []
            for rank, photo in enumerate(ranked, start=1):
                if photo is primary_keeper:
                    recommendation = "keep_candidate"
                elif photo in alternate_keepers:
                    recommendation = "alternate_keeper"
                elif rank <= candidate_keep_count + int(self.review_config.get("challenger_queue_size", 5)):
                    recommendation = "alternate"
                else:
                    recommendation = "lower_ranked"
                photos_payload.append(self.photo_payload(photo, rank, recommendation, cover))
            challenger_queue = self.cluster_challenger_queue(primary_keeper, ranked, alternate_keepers)
            keeper_slots = [self.keeper_slot_payload(1, primary_keeper, ranked, [primary_keeper])]
            sims = pairwise_similarities(group)
            set_type = self.set_type(group, sims)
            time_start, time_end = time_range(group)
            sets.append({
                "schema_version": SCHEMA_VERSION,
                "review_set_id": f"set_{idx:06d}",
                "set_type": set_type,
                "photo_count": len(group),
                "cover_display_id": cover.display_id,
                "primary_keeper_id": primary_keeper.display_id,
                "recommended_keep_count": 1,
                "recommended_keep_ids": [primary_keeper.display_id],
                "alternate_keeper_ids": [p.display_id for p in alternate_keepers],
                "alternate_keeper_count": len(alternate_keepers),
                "challenger_queue": challenger_queue,
                "time_range": {
                    "start": format_capture_time(time_start),
                    "end": format_capture_time(time_end),
                    "duration_seconds": int((time_end - time_start).total_seconds()) if time_start and time_end else 0,
                },
                "signals": {
                    "time_span_seconds": int((time_end - time_start).total_seconds()) if time_start and time_end else 0,
                    "embedding_similarity_min": round(min(sims), 6) if sims else 1.0,
                    "embedding_similarity_mean": round(sum(sims) / len(sims), 6) if sims else 1.0,
                    "embedding_similarity_max": round(max(sims), 6) if sims else 1.0,
                },
                "set_score": {
                    "best_overall": round(max(p.score["overall"] for p in group), 6),
                    "score_spread": round(max(p.score["overall"] for p in group) - min(p.score["overall"] for p in group), 6),
                },
                "keeper_slots": keeper_slots,
                "photos": photos_payload,
                "reason_summary_zh": self.set_reasons(set_type, len(group), 1, len(alternate_keepers)),
            })
            self.emit("progress", stage="review_sets", done=idx, total=total, message="Building review sets")
        return sets


    def cluster_challenger_queue(self, primary_keeper: ReviewPhoto, ranked: list[ReviewPhoto], alternate_keepers: list[ReviewPhoto]) -> list[dict[str, Any]]:
        alternate_ids = {photo.display_id for photo in alternate_keepers}
        queue = []
        for rank, challenger in enumerate([photo for photo in ranked if photo is not primary_keeper], start=1):
            queue.append({
                "photo_id": challenger.display_id,
                "rank": rank,
                "compare_to": primary_keeper.display_id,
                "is_alternate_keeper": challenger.display_id in alternate_ids,
                "similarity_to_primary": round(cosine(challenger.embedding, primary_keeper.embedding), 6),
                "score_delta": round(challenger.score["overall"] - primary_keeper.score["overall"], 6),
                "reason_zh": challenger_reason(challenger, primary_keeper),
            })
        return queue

    def rank_group(self, group: list[ReviewPhoto]) -> list[ReviewPhoto]:
        normalized = normalize_group_scores(group)
        ranked: list[tuple[float, ReviewPhoto]] = []
        for photo in group:
            norm = normalized.get(photo.display_id, {})
            blended = weighted([
                (photo.score["base_overall"], 0.75),
                (norm.get("technical_quality", photo.score["technical_quality"]), 0.1),
                (norm.get("face_quality", photo.score["face_quality"]), 0.05),
                (norm.get("iqa", photo.score["iqa"]), 0.05),
                (norm.get("composition", photo.score["composition"]), 0.05),
            ])
            photo.score["group_relative"] = blended
            photo.score["overall"] = blended
            ranked.append((blended, photo))
        return [photo for _, photo in sorted(ranked, key=lambda item: (-item[0], item[1].display_id))]

    def keep_count(self, photo_count: int) -> int:
        policy = self.review_config.get("keeper_policy", {})
        if photo_count >= int(policy.get("large_set_min_size", 9)):
            value = int(policy.get("large_set_keep_count", 3))
        elif photo_count >= int(policy.get("medium_set_min_size", 4)):
            value = int(policy.get("medium_set_keep_count", 2))
        else:
            value = int(policy.get("small_set_keep_count", 1))
        return max(1, min(photo_count, int(policy.get("max_keep_count", 3)), value))

    def set_type(self, group: list[ReviewPhoto], sims: list[float]) -> str:
        if len(group) == 1:
            return "single"
        threshold = float(self.review_config.get("near_duplicate_similarity_threshold", 0.93))
        return "near_duplicate" if sims and min(sims) >= threshold else "similar_scene"

    def photo_payload(self, photo: ReviewPhoto, rank: int, recommendation: str, cover: ReviewPhoto) -> dict[str, Any]:
        assets = photo.manifest.get("assets", {})
        return {
            "display_id": photo.display_id,
            "source_id": photo.source_id,
            "source_path": photo.manifest.get("source", {}).get("path"),
            "thumb_path": assets.get("thumb_path"),
            "thumb_width": int(assets.get("thumb_width") or 0),
            "thumb_height": int(assets.get("thumb_height") or 0),
            "preview_path": assets.get("preview_path"),
            "preview_width": int(assets.get("preview_width") or 0),
            "preview_height": int(assets.get("preview_height") or 0),
            "analysis_path": photo.manifest.get("analysis_path"),
            "capture_time": photo.capture_time_raw or format_capture_time(photo.capture_time),
            "rank": rank,
            "recommendation": recommendation,
            "ui_initial_state": recommendation_to_ui_state(recommendation),
            "similarity_to_cover": round(cosine(photo.embedding, cover.embedding), 6),
            "score": {k: round(v, 6) for k, v in photo.score.items()},
            "compare_metrics": compare_metrics_payload(photo.analysis),
            "foreground_area_ratio": photo.foreground_area_ratio,
            "has_foreground_embedding": photo.foreground_embedding is not None,
            "has_background_embedding": photo.background_embedding is not None,
            "score_missing": photo.score_missing,
            "badges": photo.badges,
            "warnings": photo.warnings,
            "reason_summary_zh": photo.reason_summary_zh,
            "weakness_summary_zh": photo.weakness_summary_zh,
        }

    def keeper_slot_payload(self, slot_idx: int, keeper: ReviewPhoto, ranked: list[ReviewPhoto], keepers: list[ReviewPhoto]) -> dict[str, Any]:
        queue_size = int(self.review_config.get("challenger_queue_size", 5))
        candidates = [p for p in ranked if p is not keeper]
        candidates.sort(key=lambda p: (-cosine(p.embedding, keeper.embedding), -p.score["overall"], p.display_id))
        queue = []
        for rank, challenger in enumerate(candidates[:queue_size], start=1):
            queue.append({
                "photo_id": challenger.display_id,
                "rank": rank,
                "similarity_to_keeper": round(cosine(challenger.embedding, keeper.embedding), 6),
                "score_delta": round(challenger.score["overall"] - keeper.score["overall"], 6),
                "reason_zh": challenger_reason(challenger, keeper),
            })
        return {
            "slot_id": f"slot_{slot_idx}",
            "keeper_photo_id": keeper.display_id,
            "rank": slot_idx,
            "confidence": round(keeper.score["overall"], 6),
            "reason_summary_zh": keeper.reason_summary_zh,
            "weakness_summary_zh": keeper.weakness_summary_zh,
            "diversity_reason_zh": diversity_reason(keeper, keepers),
            "challenger_queue": queue,
        }

    def score_photo(self, analysis: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
        missing: list[str] = []
        metrics = analysis.get("image_metrics") or {}
        sharp = metrics.get("sharpness") or {}
        exposure = metrics.get("exposure") or {}
        contrast = metrics.get("contrast") or {}
        color = metrics.get("color") or {}
        composition_metrics = metrics.get("composition") or {}
        face = analysis.get("face_metrics") or {}
        iqa_metrics = analysis.get("iqa_metrics", {}).get("metrics", {})
        iqa = iqa_metrics.get("piqe", {})
        aesthetic = iqa_metrics.get("aesthetic", {})

        if not sharp or not exposure or not contrast or not color:
            missing.append("technical_quality")
        sharpness = clamp01(math.log1p(safe_float(sharp.get("laplacian_var"))) / math.log1p(800))
        shadow = safe_float(exposure.get("shadow_clip_ratio")); highlight = safe_float(exposure.get("highlight_clip_ratio"))
        brightness = safe_float(exposure.get("brightness_mean"), 127.5)
        brightness_score = clamp01(1.0 - abs(brightness - 127.5) / 127.5)
        exposure_score = clamp01(1.0 - shadow * 8.0 - highlight * 10.0)
        contrast_score = clamp01(safe_float(contrast.get("contrast_std_ratio")) / 0.22)
        dynamic_range_score = clamp01(safe_float(exposure.get("dynamic_range_p05_p95")) / 0.45)
        saturation = safe_float(color.get("saturation_mean"), 0.35)
        color_score = clamp01(1.0 - abs(saturation - 0.35) / 0.45 - safe_float(color.get("color_cast_strength")) * 1.5)
        technical = weighted([
            (sharpness, 0.35),
            (exposure_score, 0.2),
            (brightness_score, 0.1),
            (contrast_score, 0.15),
            (dynamic_range_score, 0.1),
            (color_score, 0.1),
        ])

        face_count = int(face.get("face_count", 0) or 0)
        if face_count > 0 and face.get("faces"):
            largest = max(face["faces"], key=lambda f: safe_float(f.get("area_ratio")))
            face_sharp = clamp01(math.log1p(safe_float(largest.get("sharpness_laplacian_var"))) / math.log1p(900))
            face_size = clamp01(safe_float(largest.get("area_ratio")) / 0.04)
            align = safe_float(largest.get("alignment_score"))
            conf = safe_float(largest.get("score"))
            face_score = weighted([(face_sharp, 0.4), (face_size, 0.25), (align, 0.2), (conf, 0.15)])
        else:
            face_score = 0.5
            missing.append("face_quality")

        piqe = iqa.get("score")
        aesthetic_score = aesthetic.get("normalized_score")
        if piqe is None:
            piqe_score = None
            if aesthetic_score is None:
                missing.append("iqa")
        else:
            piqe_score = clamp01(1.0 - safe_float(piqe) / 100.0)
        if piqe_score is None and aesthetic_score is None:
            iqa_score = 0.5
        elif piqe_score is None:
            iqa_score = safe_float(aesthetic_score, 0.5)
        elif aesthetic_score is None:
            iqa_score = piqe_score
        else:
            iqa_score = weighted([(piqe_score, 0.7), (safe_float(aesthetic_score), 0.3)])

        if not composition_metrics:
            missing.append("composition")
        center_ratio = safe_float(sharp.get("center_sharpness_ratio"), 1.0)
        center_delta = abs(safe_float(composition_metrics.get("center_brightness_delta"))) / 255.0
        aspect_ratio = safe_float(composition_metrics.get("aspect_ratio"), 1.5)
        aspect_score = clamp01(1.0 - max(0.0, abs(aspect_ratio - 1.5) - 1.2) / 2.0)
        composition = weighted([(clamp01(center_ratio / 1.5), 0.45), (clamp01(1.0 - center_delta * 2.0), 0.35), (aspect_score, 0.2)])
        base_overall = weighted([(technical, 0.35), (face_score, 0.2 if face_count else 0.05), (iqa_score, 0.25), (composition, 0.2)])
        return {
            "overall": base_overall,
            "base_overall": base_overall,
            "technical_quality": technical,
            "face_quality": face_score,
            "iqa": iqa_score,
            "composition": composition,
        }, missing

    def explain_photo(self, analysis: dict[str, Any], score: dict[str, float], missing: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
        badges: list[str] = []
        warnings: list[str] = []
        reasons: list[str] = []
        weaknesses: list[str] = []
        if score["technical_quality"] >= 0.75:
            badges.append("technical_good"); reasons.append("技术质量较好")
        if score["face_quality"] >= 0.75 and analysis.get("face_metrics", {}).get("face_count", 0):
            badges.append("face_good"); reasons.append("人脸质量较好")
        if score["iqa"] >= 0.7:
            badges.append("iqa_good"); reasons.append("IQA 质量分较好")
        exposure = analysis.get("image_metrics", {}).get("exposure", {})
        if safe_float(exposure.get("highlight_clip_ratio")) > 0.03:
            warnings.append("highlight_clip"); weaknesses.append("高光裁切偏多")
        if safe_float(exposure.get("shadow_clip_ratio")) > 0.05:
            warnings.append("shadow_clip"); weaknesses.append("暗部裁切偏多")
        if safe_float(exposure.get("brightness_mean"), 127.5) < 70:
            warnings.append("underexposed"); weaknesses.append("整体亮度偏暗")
        if safe_float(exposure.get("brightness_mean"), 127.5) > 190:
            warnings.append("overexposed"); weaknesses.append("整体亮度偏亮")
        for item in missing:
            weaknesses.append(f"缺少 {item} 数据")
        if not reasons:
            reasons.append("组内综合评分可用")
        if not weaknesses:
            weaknesses.append("暂无明显弱点")
        return badges, warnings, reasons, weaknesses

    def set_reasons(self, set_type: str, photo_count: int, primary_keep_count: int, alternate_keep_count: int = 0) -> list[str]:
        if set_type == "single":
            return ["单张照片，无需组内对比", "建议保留该组唯一照片"]
        reasons = ["同一时间段内视觉相似", f"系统默认给出 {primary_keep_count} 张主推荐", f"该组共有 {photo_count} 张候选"]
        if alternate_keep_count:
            reasons.append(f"另有 {alternate_keep_count} 张质量较高的备选保留候选")
        return reasons

    def build_summary(self, review_sets: list[dict[str, Any]], photos: list[ReviewPhoto], input_hash: str) -> dict[str, Any]:
        type_counts: dict[str, int] = {}
        for item in review_sets:
            type_counts[item["set_type"]] = type_counts.get(item["set_type"], 0) + 1
        keep_count = sum(len(item.get("recommended_keep_ids", [])) for item in review_sets)
        alternate_keep_count = sum(len(item.get("alternate_keeper_ids", [])) for item in review_sets)
        challenger_count = sum(len(item.get("challenger_queue", [])) for item in review_sets)
        keeper_slot_count = sum(len(item.get("keeper_slots", [])) for item in review_sets)
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "success",
            "folder": str(self.folder),
            "cache_dir": str(self.cache_dir),
            "input_manifest_path": ".cullary/manifest.jsonl",
            "review_sets_path": ".cullary/review_sets.jsonl",
            "total_photos": len(photos),
            "review_set_count": len(review_sets),
            "single_count": type_counts.get("single", 0),
            "near_duplicate_count": type_counts.get("near_duplicate", 0),
            "similar_scene_count": type_counts.get("similar_scene", 0),
            "recommended_keep_count": keep_count,
            "alternate_keeper_count": alternate_keep_count,
            "keeper_slot_count": keeper_slot_count,
            "challenger_count": challenger_count,
            "lower_ranked_count": sum(
                1
                for item in review_sets
                for photo in item.get("photos", [])
                if photo.get("recommendation") == "lower_ranked"
            ),
            "duration_ms": int((time.perf_counter() - self.started_perf) * 1000),
            "config_hash": config_hash(self.config, "review"),
            "input_hash": input_hash,
            "cache_hit": False,
            "generated_at": now_iso(),
            "failures": getattr(self, "skipped_inputs", []),
        }


def parse_capture_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ["%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
        try:
            return datetime.strptime(str(value).split("+")[0], fmt)
        except ValueError:
            continue
    return None


def format_capture_time(value: datetime | None) -> str | None:
    return value.strftime("%Y:%m:%d %H:%M:%S") if value else None


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def time_distance_seconds(a: ReviewPhoto, b: ReviewPhoto) -> float:
    if not a.capture_time or not b.capture_time:
        return 0.0
    return abs((b.capture_time - a.capture_time).total_seconds())


def pairwise_similarities(group: list[ReviewPhoto]) -> list[float]:
    return [cosine(group[i].embedding, group[j].embedding) for i in range(len(group)) for j in range(i + 1, len(group))]


def time_range(group: list[ReviewPhoto]) -> tuple[datetime | None, datetime | None]:
    times = [p.capture_time for p in group if p.capture_time]
    return (min(times), max(times)) if times else (None, None)


def safe_float(value: Any, default: Any = 0.0) -> Any:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def load_normalized_vector(path: Path) -> np.ndarray:
    embedding = np.load(path).astype("float32").reshape(-1)
    norm = float(np.linalg.norm(embedding))
    return embedding / norm if norm > 0 else embedding


def load_optional_embedding(payload: Any, folder: Path) -> np.ndarray | None:
    if not isinstance(payload, dict) or payload.get("status") == "failed":
        return None
    vector_path = payload.get("vector_path")
    if not vector_path:
        return None
    path = Path(vector_path)
    path = path if path.is_absolute() else folder / path
    if not path.exists():
        return None
    return load_normalized_vector(path)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, safe_float(value)))


def weighted(items: list[tuple[float, float]]) -> float:
    total_w = sum(w for _, w in items if w > 0)
    return clamp01(sum(clamp01(v) * w for v, w in items if w > 0) / total_w) if total_w else 0.0


def normalize_group_scores(group: list[ReviewPhoto]) -> dict[str, dict[str, float]]:
    categories = ["technical_quality", "face_quality", "iqa", "composition"]
    normalized: dict[str, dict[str, float]] = {photo.display_id: {} for photo in group}
    for category in categories:
        values = [photo.score[category] for photo in group if category not in photo.score_missing]
        if len(values) <= 1:
            for photo in group:
                normalized[photo.display_id][category] = photo.score[category]
            continue
        low = percentile(values, 10)
        high = percentile(values, 90)
        if abs(high - low) < 1e-9:
            for photo in group:
                normalized[photo.display_id][category] = 0.5
            continue
        for photo in group:
            normalized[photo.display_id][category] = clamp01((photo.score[category] - low) / (high - low))
    return normalized


def compare_metrics_payload(analysis: dict[str, Any]) -> dict[str, Any]:
    metrics = analysis.get("image_metrics") or {}
    sharp = metrics.get("sharpness") or {}
    exposure = metrics.get("exposure") or {}
    contrast = metrics.get("contrast") or {}
    color = metrics.get("color") or {}
    composition = metrics.get("composition") or {}
    experimental = metrics.get("experimental") or {}
    face = analysis.get("face_metrics") or {}
    faces = face.get("faces") or []
    largest_face = max(faces, key=lambda item: safe_float(item.get("area_ratio"))) if faces else {}
    iqa_metrics = analysis.get("iqa_metrics", {}).get("metrics", {})
    piqe = iqa_metrics.get("piqe", {})
    aesthetic = iqa_metrics.get("aesthetic", {})

    values = {
        "sharpness": clamp01(math.log1p(safe_float(sharp.get("laplacian_var"))) / math.log1p(800)),
        "center_sharpness": clamp01(safe_float(sharp.get("center_sharpness_ratio"), 1.0) / 1.5),
        "exposure_clip": clamp01(1.0 - safe_float(exposure.get("shadow_clip_ratio")) * 8.0 - safe_float(exposure.get("highlight_clip_ratio")) * 10.0),
        "brightness": clamp01(1.0 - abs(safe_float(exposure.get("brightness_mean"), 127.5) - 127.5) / 127.5),
        "contrast": clamp01(safe_float(contrast.get("contrast_std_ratio")) / 0.22),
        "dynamic_range": clamp01(safe_float(exposure.get("dynamic_range_p05_p95")) / 0.45),
        "saturation": clamp01(1.0 - abs(safe_float(color.get("saturation_mean"), 0.35) - 0.35) / 0.45),
        "color_cast": clamp01(1.0 - safe_float(color.get("color_cast_strength")) * 1.5),
        "piqe": clamp01(1.0 - safe_float(piqe.get("score")) / 100.0) if piqe.get("score") is not None else None,
        "aesthetic": clamp01(safe_float(aesthetic.get("normalized_score"))) if aesthetic.get("normalized_score") is not None else None,
        "face_sharpness": clamp01(math.log1p(safe_float(largest_face.get("sharpness_laplacian_var"))) / math.log1p(900)) if largest_face else None,
        "face_size": clamp01(safe_float(largest_face.get("area_ratio")) / 0.04) if largest_face else None,
        "face_alignment": clamp01(safe_float(largest_face.get("alignment_score"))) if largest_face else None,
        "center_brightness": clamp01(1.0 - abs(safe_float(composition.get("center_brightness_delta"))) / 255.0 * 2.0),
        "aspect": clamp01(1.0 - max(0.0, abs(safe_float(composition.get("aspect_ratio"), 1.5) - 1.5) - 1.2) / 2.0),
    }
    raw = {
        "brightness_mean": exposure.get("brightness_mean"),
        "brightness_p05": exposure.get("brightness_p05"),
        "brightness_p50": exposure.get("brightness_median"),
        "brightness_p95": exposure.get("brightness_p95"),
        "brightness_histogram": exposure.get("brightness_histogram"),
        "brightness_histogram_16": exposure.get("brightness_histogram_16"),
        "rgb_histogram": exposure.get("rgb_histogram"),
        "shadow_clip_ratio": exposure.get("shadow_clip_ratio"),
        "highlight_clip_ratio": exposure.get("highlight_clip_ratio"),
        "laplacian_var": sharp.get("laplacian_var"),
        "center_sharpness_ratio": sharp.get("center_sharpness_ratio"),
        "contrast_std_ratio": contrast.get("contrast_std_ratio"),
        "dynamic_range_p05_p95": exposure.get("dynamic_range_p05_p95"),
        "saturation_mean": color.get("saturation_mean"),
        "color_cast_strength": color.get("color_cast_strength"),
        "piqe": piqe.get("score"),
        "aesthetic": aesthetic.get("normalized_score"),
        "face_count": face.get("face_count"),
        "face_area_ratio": largest_face.get("area_ratio") if largest_face else None,
        "face_sharpness_laplacian_var": largest_face.get("sharpness_laplacian_var") if largest_face else None,
        "face_alignment_score": largest_face.get("alignment_score") if largest_face else None,
        "center_brightness_delta": composition.get("center_brightness_delta"),
        "aspect_ratio": composition.get("aspect_ratio"),
        "noise_proxy": experimental.get("noise_proxy"),
    }
    return {
        "values": {key: round(value, 6) for key, value in values.items() if value is not None},
        "raw": {key: value for key, value in raw.items() if value is not None},
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[int(pos)]
    return ordered[lower] * (upper - pos) + ordered[upper] * (pos - lower)


def recommendation_to_ui_state(recommendation: str) -> str:
    return {
        "keep_candidate": "recommended_keep",
        "alternate_keeper": "recommended_alternate",
        "alternate": "user_undecided",
        "lower_ranked": "not_prioritized",
    }.get(recommendation, "not_prioritized")


def challenger_reason(challenger: ReviewPhoto, keeper: ReviewPhoto) -> str:
    if challenger.score["overall"] >= keeper.score["overall"]:
        return "综合评分接近或更高，值得对比"
    if challenger.score["face_quality"] > keeper.score["face_quality"]:
        return "人脸质量更好，但综合评分略低"
    return "视觉相似度较高，可作为对比候选"


def diversity_reason(keeper: ReviewPhoto, keepers: list[ReviewPhoto]) -> str:
    others = [p for p in keepers if p is not keeper]
    if not others:
        return "该组首选 keeper"
    max_sim = max(cosine(keeper.embedding, other.embedding) for other in others)
    return "与其他推荐图有一定差异" if max_sim < 0.95 else "与其他推荐图较相似，但质量排名靠前"
