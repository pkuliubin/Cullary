from __future__ import annotations

from pathlib import Path
from typing import Any

from .media import make_resized_jpeg


class IqaAnalyzer:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._metric: Any | None = None

    def analyze(self, preview_path: Path, input_path: Path) -> tuple[dict[str, Any] | None, str | None]:
        if not self.config.get("enabled", True):
            return {"enabled": False}, None
        metric_name = self.config.get("metric", "piqe")
        try:
            import pyiqa
        except Exception as exc:
            return None, f"missing iqa dependency: {exc}"
        if self._metric is None:
            self._metric = pyiqa.create_metric(metric_name, device="cpu")
        max_side = int(self.config.get("max_side", 512))
        make_resized_jpeg(preview_path, input_path, max_side)
        score = self._metric(str(input_path))
        if hasattr(score, "detach"):
            value = float(score.detach().cpu().flatten()[0])
        else:
            value = float(score)
        return {
            "input": {"max_side": max_side, "path": None},
            "metrics": {metric_name: {"score": round(value, 6), "direction": "lower_is_better"}},
        }, None
