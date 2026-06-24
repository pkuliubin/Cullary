from __future__ import annotations

from pathlib import Path
from typing import Any


class EmbeddingAnalyzer:
    def __init__(self, models_dir: Path, config: dict[str, Any]) -> None:
        self.models_dir = models_dir
        self.config = config
        self._backend: tuple[Any, Any, str] | None = None

    def analyze(self, preview_path: Path, output_path: Path) -> tuple[dict[str, Any] | None, str | None]:
        if not self.config.get("enabled", True):
            return {"enabled": False}, None
        try:
            from PIL import Image
        except Exception as exc:
            return None, f"missing embedding dependency: {exc}"
        image = Image.open(preview_path).convert("RGB")
        result = self.analyze_batch([(image, output_path)])[0]
        return result

    def analyze_batch(self, items: list[tuple[Any, Path]]) -> list[tuple[dict[str, Any] | None, str | None]]:
        if not self.config.get("enabled", True):
            return [({"enabled": False}, None) for _ in items]
        if not items:
            return []
        try:
            import numpy as np
            import torch
        except Exception as exc:
            return [(None, f"missing embedding dependency: {exc}") for _ in items]
        backend = self._load_backend()
        if backend is None:
            return [(None, "embedding model files missing") for _ in items]
        processor, model, kind = backend
        try:
            images = [image for image, _ in items]
            inputs = processor(images=images, return_tensors="pt")
            with torch.inference_mode():
                outputs = model(**inputs)
                if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
                    embedding = outputs.pooler_output
                else:
                    embedding = outputs.last_hidden_state.mean(dim=1)
                if self.config.get("normalize", True):
                    embedding = torch.nn.functional.normalize(embedding, p=2, dim=-1)
            arrays = embedding.detach().cpu().numpy().astype("float32")
            results: list[tuple[dict[str, Any] | None, str | None]] = []
            for arr, (_, output_path) in zip(arrays, items):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                np.save(output_path, arr.reshape(-1))
                results.append(({
                    "model": self.config.get("model", "dinov2-small"),
                    "model_version": self.config.get("model_version", "facebook/dinov2-small"),
                    "kind": kind,
                    "dim": int(arr.reshape(-1).shape[0]),
                    "input_size": self.config.get("input_size", "processor_default"),
                    "batch_size": len(items),
                    "normalized": bool(self.config.get("normalize", True)),
                    "vector_path": None,
                    "preview_source": "preview_path",
                }, None))
            return results
        except Exception as exc:
            return [(None, f"{type(exc).__name__}: {exc}") for _ in items]

    def _load_backend(self) -> tuple[Any, Any, str] | None:
        if self._backend is not None:
            return self._backend
        try:
            from transformers import AutoImageProcessor, AutoModel
        except Exception:
            return None
        model_path = self.models_dir / self.config.get("model_path", "hf-direct/facebook__dinov2-small")
        if not model_path.exists():
            return None
        processor = AutoImageProcessor.from_pretrained(str(model_path), local_files_only=True)
        model = AutoModel.from_pretrained(str(model_path), local_files_only=True)
        model.eval()
        self._backend = (processor, model, "vision")
        return self._backend
