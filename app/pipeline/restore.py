import cv2
import numpy as np


def restore(gray):
    """Restore faded text with deterministic image processing (never invents characters)."""
    g = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    g = cv2.fastNlMeansDenoising(g, None, 10, 7, 21)
    bg = cv2.medianBlur(cv2.dilate(g, np.ones((5, 5), np.uint8)), 31)
    norm = cv2.divide(g, bg, scale=255).astype(np.float32)
    lo, hi = np.percentile(norm, (1, 90))
    out = np.clip((norm - lo) * 255.0 / max(hi - lo, 1.0), 0, 255).astype(np.uint8)
    return out