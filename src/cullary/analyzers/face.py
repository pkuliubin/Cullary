from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .image_metrics import laplacian_var


class FaceAnalyzer:
    def __init__(self, models_dir: Path, config: dict[str, Any]) -> None:
        self.models_dir = models_dir
        self.config = config
        self._detector: Any | None = None

    def analyze(self, preview_path: Path) -> tuple[dict[str, Any] | None, str | None]:
        if not self.config.get("enabled", True):
            return {"enabled": False}, None
        try:
            import cv2
        except Exception as exc:
            return None, f"missing face dependency: {exc}"
        detector = self._load_yunet(cv2)
        if detector is None:
            return None, "YuNet model file missing or OpenCV FaceDetectorYN unavailable"
        bgr = cv2.imread(str(preview_path), cv2.IMREAD_COLOR)
        if bgr is None:
            return None, "cv2.imread failed"
        h0, w0 = bgr.shape[:2]
        max_side = int(self.config.get("max_side", 1280))
        scale = min(1.0, max_side / max(h0, w0))
        work = cv2.resize(bgr, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else bgr
        hw, ww = work.shape[:2]
        detector.setInputSize((ww, hw))
        _, detections = detector.detect(work)
        gray_full = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        faces = []
        if detections is not None:
            for row in detections:
                x, y, bw, bh = [float(v) / scale for v in row[:4]]
                score = float(row[-1])
                landmarks_flat = [float(v) / scale for v in row[4:14]]
                lms = list(zip(landmarks_flat[0::2], landmarks_flat[1::2]))
                x0, y0 = max(0, int(x)), max(0, int(y))
                x1, y1 = min(w0, int(x + bw)), min(h0, int(y + bh))
                crop = gray_full[y0:y1, x0:x1]
                left_eye, right_eye = lms[0], lms[1]
                eye_distance = math.dist(left_eye, right_eye)
                eye_angle = math.degrees(math.atan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0]))
                faces.append({
                    "box": {"x": round(x, 2), "y": round(y, 2), "w": round(bw, 2), "h": round(bh, 2)},
                    "score": round(score, 6),
                    "area_ratio": round((bw * bh) / max(w0 * h0, 1), 8),
                    "center": {"x": round(x + bw / 2, 2), "y": round(y + bh / 2, 2)},
                    "landmarks": {
                        "left_eye": [round(lms[0][0], 2), round(lms[0][1], 2)],
                        "right_eye": [round(lms[1][0], 2), round(lms[1][1], 2)],
                        "nose": [round(lms[2][0], 2), round(lms[2][1], 2)],
                        "left_mouth": [round(lms[3][0], 2), round(lms[3][1], 2)],
                        "right_mouth": [round(lms[4][0], 2), round(lms[4][1], 2)],
                    },
                    "eye_distance": round(eye_distance, 4),
                    "eye_angle_deg": round(eye_angle, 4),
                    "sharpness_laplacian_var": round(laplacian_var(crop), 4),
                    "alignment_score": round(max(0.0, 1.0 - min(abs(eye_angle), 45.0) / 45.0), 6),
                })
        return {
            "model": "yunet",
            "input": {"max_side": max_side, "scale": round(scale, 6)},
            "face_count": len(faces),
            "largest_face_area_ratio": max([f["area_ratio"] for f in faces], default=0.0),
            "faces": faces,
        }, None

    def _load_yunet(self, cv2: Any) -> Any | None:
        if self._detector is not None:
            return self._detector
        model_path = self.models_dir / self.config.get("model_path", "yunet/face_detection_yunet_2023mar.onnx")
        if not model_path.exists() or not hasattr(cv2, "FaceDetectorYN_create"):
            return None
        self._detector = cv2.FaceDetectorYN_create(
            str(model_path),
            "",
            (320, 320),
            float(self.config.get("score_threshold", 0.6)),
            float(self.config.get("nms_threshold", 0.3)),
            int(self.config.get("top_k", 5000)),
        )
        return self._detector
