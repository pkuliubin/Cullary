from __future__ import annotations

from pathlib import Path
from typing import Any


def bits_to_hex(bits: Any) -> str:
    flat = [1 if bool(v) else 0 for v in bits.ravel()]
    value = 0
    for bit in flat:
        value = (value << 1) | bit
    return f"{value:0{max(1, len(flat) // 4)}x}"


def average_hash(image: Any, np: Any) -> str:
    arr = np.asarray(image.resize((8, 8)), dtype=np.float32)
    return bits_to_hex(arr > arr.mean())


def difference_hash(image: Any, np: Any) -> str:
    arr = np.asarray(image.resize((9, 8)), dtype=np.float32)
    return bits_to_hex(arr[:, 1:] > arr[:, :-1])


def perceptual_hash(image: Any, np: Any) -> str:
    arr = np.asarray(image.resize((32, 32)), dtype=np.float32)
    try:
        import cv2

        coeff = cv2.dct(arr)[:8, :8]
    except Exception:
        coeff = np.abs(np.fft.fft2(arr))[:8, :8]
    flat = coeff.flatten()
    bits = flat > np.median(flat[1:])
    return bits_to_hex(bits)


def compute_hashes(preview_path: Path) -> dict[str, str]:
    from PIL import Image
    import numpy as np

    image = Image.open(preview_path).convert("L")
    return {
        "ahash": average_hash(image, np),
        "dhash": difference_hash(image, np),
        "phash": perceptual_hash(image, np),
    }
