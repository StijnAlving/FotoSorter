"""Heuristic sharpness/exposure scoring. Thresholds live in config/settings.json
and can be tuned in the settings dialog - these are estimates, not certainties,
which is why low-quality photos are filed into a separate folder rather than
deleted."""
import cv2
import numpy as np
from PIL import Image


def to_gray_array(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("L"))


def compute_sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian - low variance means few sharp edges, i.e.
    likely out of focus or motion-blurred."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def compute_exposure(gray: np.ndarray) -> dict:
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    total = gray.size
    return {
        "mean": float(gray.mean()),
        "clip_low_frac": float(hist[0] / total),
        "clip_high_frac": float(hist[255] / total),
    }


def classify_quality(sharpness: float, exposure: dict, settings: dict) -> tuple[bool, list[str]]:
    reasons = []
    if sharpness < settings["sharpness_threshold"]:
        reasons.append(f"blurry (sharpness={sharpness:.1f})")
    if exposure["mean"] < settings["exposure_dark_mean_threshold"]:
        reasons.append(f"underexposed (mean={exposure['mean']:.1f})")
    elif exposure["mean"] > settings["exposure_bright_mean_threshold"]:
        reasons.append(f"overexposed (mean={exposure['mean']:.1f})")
    clip_frac = exposure["clip_low_frac"] + exposure["clip_high_frac"]
    if clip_frac > settings["exposure_clip_fraction_threshold"]:
        reasons.append(f"clipped highlights/shadows ({clip_frac:.0%})")
    return bool(reasons), reasons
