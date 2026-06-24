from __future__ import annotations

from typing import Any


def default_score_features() -> dict[str, Any]:
    return {
        "technical_quality": {"score": None, "components": {"sharpness": {"weight": 0.45, "value": None}, "exposure": {"weight": 0.25, "value": None}, "contrast": {"weight": 0.15, "value": None}, "color": {"weight": 0.15, "value": None}}},
        "face_quality": {"score": None, "components": {"face_sharpness": {"weight": 0.4, "value": None}, "face_size": {"weight": 0.25, "value": None}, "alignment": {"weight": 0.2, "value": None}, "detection_confidence": {"weight": 0.15, "value": None}}},
        "iqa": {"score": None, "components": {"piqe": {"weight": 1.0, "value": None}}},
        "composition": {"score": None, "components": {"center_sharpness": {"weight": 0.5, "value": None}, "center_brightness": {"weight": 0.3, "value": None}, "orientation": {"weight": 0.2, "value": None}}},
    }
