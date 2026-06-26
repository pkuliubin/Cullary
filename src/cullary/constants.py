from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = "1.0"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".heif", ".3fr"}
IGNORED_NAMES = {".DS_Store"}
DEFAULT_INPUT = Path("/Users/liubin/Desktop/TestImage")
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "preprocess.default.json"

ANALYZER_VERSIONS = {
    "scan": "scan-v1",
    "metadata": "exiftool-json-v1",
    "preview": "preview-extract-v2",
    "thumb": "thumb-v1",
    "hash": "hash-ahash-dhash-phash-v2",
    "image_metrics": "image-metrics-v1",
    "face": "opencv-yunet-v1",
    "person_mask": "mediapipe-selfie-segmentation-v1",
    "embedding": "dinov2-small-transformers-v2",
    "iqa": "pyiqa-piqe-laion-aesthetic-v2",
}

PIPELINE_STAGES = ["scan", "metadata", "preview", "thumb", "hash", "face", "person_mask", "image_metrics", "embedding", "iqa"]
DEPENDENCIES = {
    "thumb": ["preview"],
    "hash": ["preview"],
    "face": ["preview"],
    "person_mask": ["preview", "face"],
    "image_metrics": ["preview", "person_mask"],
    "embedding": ["preview", "person_mask"],
    "iqa": ["preview"],
}
