from __future__ import annotations

from pathlib import Path
from typing import Any

from .media import make_resized_jpeg


class IqaAnalyzer:
    def __init__(self, models_dir: Path, config: dict[str, Any]) -> None:
        self.models_dir = models_dir
        self.config = config
        self._piqe_metric: Any | None = None
        self._aesthetic_backend: tuple[Any, Any, Any, Any] | None = None

    def batch_size(self) -> int:
        device_name = self.resolve_aesthetic_device_name()
        if device_name == "mps" and self.config.get("aesthetic_mps_batch_size"):
            return max(1, int(self.config["aesthetic_mps_batch_size"]))
        if device_name == "cpu" and self.config.get("aesthetic_cpu_batch_size"):
            return max(1, int(self.config["aesthetic_cpu_batch_size"]))
        return max(1, int(self.config.get("batch_size", 8)))

    def analyze(self, preview_path: Path, input_path: Path) -> tuple[dict[str, Any] | None, str | None]:
        return self.analyze_batch([(preview_path, input_path)])[0]

    def analyze_batch(self, items: list[tuple[Path, Path]]) -> list[tuple[dict[str, Any] | None, str | None]]:
        if not self.config.get("enabled", True):
            return [({"enabled": False}, None) for _ in items]
        if not items:
            return []
        payloads: list[dict[str, Any]] = [{"metrics": {}} for _ in items]
        errors: list[str | None] = [None for _ in items]
        self._add_piqe_scores(items, payloads, errors)
        self._add_aesthetic_scores(items, payloads, errors)
        results: list[tuple[dict[str, Any] | None, str | None]] = []
        for payload, error in zip(payloads, errors):
            if payload.get("metrics"):
                results.append((payload, error))
            else:
                results.append((None, error))
        return results

    def _add_piqe_scores(self, items: list[tuple[Path, Path]], payloads: list[dict[str, Any]], errors: list[str | None]) -> None:
        metric_name = self.config.get("metric", "piqe")
        try:
            import pyiqa
        except Exception as exc:
            for idx in range(len(items)):
                errors[idx] = append_error(errors[idx], f"missing iqa dependency: {exc}")
            return
        if self._piqe_metric is None:
            self._piqe_metric = pyiqa.create_metric(metric_name, device="cpu")
        max_side = int(self.config.get("max_side", 512))
        for idx, (preview_path, input_path) in enumerate(items):
            try:
                make_resized_jpeg(preview_path, input_path, max_side)
                score = self._piqe_metric(str(input_path))
                if hasattr(score, "detach"):
                    value = float(score.detach().cpu().flatten()[0])
                else:
                    value = float(score)
                payloads[idx]["input"] = {"max_side": max_side, "path": None}
                payloads[idx]["metrics"][metric_name] = {"score": round(value, 6), "direction": "lower_is_better"}
            except Exception as exc:
                errors[idx] = append_error(errors[idx], f"{metric_name}: {type(exc).__name__}: {exc}")

    def _add_aesthetic_scores(self, items: list[tuple[Path, Path]], payloads: list[dict[str, Any]], errors: list[str | None]) -> None:
        aesthetic_config = self.config.get("aesthetic", {})
        if not aesthetic_config.get("enabled", True):
            return
        backend = self._load_aesthetic_backend()
        if backend is None:
            for idx in range(len(items)):
                payloads[idx]["metrics"]["aesthetic"] = {"status": "failed", "error_message": "aesthetic model files missing"}
                errors[idx] = append_error(errors[idx], "aesthetic: model files missing")
            return
        try:
            import torch
            from PIL import Image
        except Exception as exc:
            for idx in range(len(items)):
                payloads[idx]["metrics"]["aesthetic"] = {"status": "failed", "error_message": f"missing aesthetic dependency: {exc}"}
                errors[idx] = append_error(errors[idx], f"aesthetic: missing dependency: {exc}")
            return
        processor, model, head, device = backend
        try:
            images = [Image.open(preview_path).convert("RGB") for preview_path, _ in items]
            inputs = processor(images=images, return_tensors="pt")
            inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
            with torch.inference_mode():
                features = model.get_image_features(**inputs)
                features = torch.nn.functional.normalize(features, p=2, dim=-1)
                scores = head(features).flatten()
            sync_torch_device(device, torch)
            values = [float(value) for value in scores.detach().cpu()]
            for idx, value in enumerate(values):
                normalized = normalize_aesthetic_score(value)
                payloads[idx]["metrics"]["aesthetic"] = {
                    "score": round(value, 6),
                    "normalized_score": round(normalized, 6),
                    "direction": "higher_is_better",
                    "model": aesthetic_config.get("model", "laion-aesthetic-predictor-v1"),
                    "clip_model": aesthetic_config.get("clip_model", "openai/clip-vit-base-patch32"),
                    "clip_head": "vit_b_32",
                    "device": str(device),
                    "batch_size": len(items),
                }
        except Exception as exc:
            for idx in range(len(items)):
                payloads[idx]["metrics"]["aesthetic"] = {"status": "failed", "error_message": f"{type(exc).__name__}: {exc}"}
                errors[idx] = append_error(errors[idx], f"aesthetic: {type(exc).__name__}: {exc}")

    def resolve_aesthetic_device_name(self) -> str:
        requested = str(self.config.get("aesthetic_device", self.config.get("device", "auto"))).lower()
        try:
            import torch
        except Exception:
            return "cpu"
        if requested == "auto":
            if torch.backends.mps.is_available():
                return "mps"
            if torch.cuda.is_available():
                return "cuda"
            return "cpu"
        if requested == "mps" and not torch.backends.mps.is_available():
            return "cpu" if self.config.get("device_fallback", True) else "mps"
        if requested == "cuda" and not torch.cuda.is_available():
            return "cpu" if self.config.get("device_fallback", True) else "cuda"
        return requested

    def _load_aesthetic_backend(self) -> tuple[Any, Any, Any, Any] | None:
        if self._aesthetic_backend is not None:
            return self._aesthetic_backend
        aesthetic_config = self.config.get("aesthetic", {})
        try:
            import torch
            import torch.nn as nn
            from transformers import CLIPModel, CLIPProcessor
        except Exception:
            return None
        clip_path = self.models_dir / aesthetic_config.get("clip_model_path", "hf-direct/openai__clip-vit-base-patch32")
        head_path = self.models_dir / aesthetic_config.get("head_path", "laion-aesthetic/sa_0_4_vit_b_32_linear.pth")
        if not clip_path.exists() or not head_path.exists():
            return None
        processor = CLIPProcessor.from_pretrained(str(clip_path), local_files_only=True)
        model = CLIPModel.from_pretrained(str(clip_path), local_files_only=True)
        head = nn.Linear(512, 1)
        head.load_state_dict(torch.load(head_path, map_location="cpu"))
        device = torch.device(self.resolve_aesthetic_device_name())
        model.eval().to(device)
        head.eval().to(device)
        sync_torch_device(device, torch)
        self._aesthetic_backend = (processor, model, head, device)
        return self._aesthetic_backend


def append_error(existing: str | None, message: str) -> str:
    return f"{existing}; {message}" if existing else message


def normalize_aesthetic_score(score: float) -> float:
    # LAION scores are commonly around 1..10. Clamp to a stable 0..1 feature.
    return max(0.0, min(1.0, score / 10.0))


def sync_torch_device(device: Any, torch_module: Any) -> None:
    if device.type == "mps":
        torch_module.mps.synchronize()
    elif device.type == "cuda":
        torch_module.cuda.synchronize(device)
