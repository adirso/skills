"""Objective, explainable technical-quality signals.

Every signal is reported separately and normalized to 0..1 (1 = better), plus the raw
measurement. The combined `technical` score is a transparent weighted mean; it is a
ranking aid, never a reason to discard a photo on its own.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Optional

import cv2
import numpy as np

QUALITY_VERSION = 1
ANALYSIS_SIZE = 1024


@dataclass
class QualityResult:
    sharpness: float
    exposure: float
    brightness: float  # mean luminance 0..1 (raw, not a score)
    highlights_clipped: float  # fraction of pixels
    shadows_clipped: float
    contrast: float
    noise: float  # 1 = clean
    colorfulness: float
    composition: float
    technical: float
    details: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return asdict(self)


def _scale(v: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return float(min(1.0, max(0.0, (v - lo) / (hi - lo))))


def laplacian_var(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F, ksize=3).var())


def sharpness_score_from_var(v: float) -> float:
    # log scale: var ~10 is very blurry, ~300+ is crisp at 1024px analysis size
    return _scale(math.log10(max(v, 1e-3)), 1.0, 2.5)


def tiled_sharpness(gray: np.ndarray, grid: int = 4) -> tuple[float, float]:
    """Return (global laplacian variance, 90th-percentile tile variance).

    Using the sharpest tiles avoids penalizing intentional background blur (bokeh)."""
    h, w = gray.shape
    vals = []
    for i in range(grid):
        for j in range(grid):
            tile = gray[i * h // grid:(i + 1) * h // grid, j * w // grid:(j + 1) * w // grid]
            if tile.size > 64:
                vals.append(laplacian_var(tile))
    return laplacian_var(gray), float(np.percentile(vals, 90)) if vals else 0.0


def estimate_noise(gray: np.ndarray) -> float:
    """Immerkær (1996) fast noise variance estimation; returns sigma in 0..255 units."""
    g = gray.astype(np.float64)
    h, w = g.shape
    if h < 3 or w < 3:
        return 0.0
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)
    conv = cv2.filter2D(g, -1, k)
    # Only measure in flat-ish regions so texture is not mistaken for noise
    edges = cv2.Canny(gray, 50, 150)
    mask = cv2.dilate(edges, np.ones((5, 5), np.uint8)) == 0
    vals = np.abs(conv[1:-1, 1:-1][mask[1:-1, 1:-1]])
    if vals.size < 1000:
        vals = np.abs(conv[1:-1, 1:-1]).ravel()
    return float(math.sqrt(math.pi / 2) * vals.mean() / 6.0)


def colorfulness(bgr: np.ndarray) -> float:
    """Hasler & Süsstrunk (2003) colorfulness metric."""
    b, g, r = [c.astype(np.float64) for c in cv2.split(bgr)]
    rg = r - g
    yb = 0.5 * (r + g) - b
    return float(math.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * math.sqrt(rg.mean() ** 2 + yb.mean() ** 2))


def composition_score(face_boxes: list[tuple[float, float, float, float]], saliency_center: Optional[tuple[float, float]]) -> tuple[float, dict]:
    """Heuristic composition score.

    - Subject (largest faces, else saliency centroid) near a rule-of-thirds line or centered.
    - Faces cut by the frame edge are penalized.
    Returns (score, explanation)."""
    info: dict = {}
    if face_boxes:
        boxes = sorted(face_boxes, key=lambda b: b[2] * b[3], reverse=True)[:3]
        cx = float(np.mean([b[0] + b[2] / 2 for b in boxes]))
        cy = float(np.mean([b[1] + b[3] / 2 for b in boxes]))
        cut = sum(1 for b in face_boxes if b[0] < 0.005 or b[1] < 0.005 or b[0] + b[2] > 0.995 or b[1] + b[3] > 0.995)
        info["faces_cut_by_edge"] = cut
        info["subject"] = "faces"
    elif saliency_center:
        cx, cy = saliency_center
        cut = 0
        info["subject"] = "saliency"
    else:
        return 0.5, {"subject": "unknown"}
    thirds = [1 / 3, 1 / 2, 2 / 3]
    dx = min(abs(cx - t) for t in thirds)
    # Vertical: faces usually look best in the upper half/third
    dy = min(abs(cy - t) for t in (1 / 3, 0.45))
    placement = 1.0 - min(1.0, (dx + dy) / 0.35)
    score = 0.4 + 0.6 * placement - 0.25 * min(cut, 2)
    info["subject_center"] = [round(cx, 3), round(cy, 3)]
    return float(min(1.0, max(0.0, score))), info


def spectral_saliency_center(gray: np.ndarray) -> Optional[tuple[float, float]]:
    """Spectral-residual saliency (Hou & Zhang 2007) centroid, normalized coordinates."""
    small = cv2.resize(gray, (64, 64)).astype(np.float32)
    f = np.fft.fft2(small)
    log_amp = np.log(np.abs(f) + 1e-8)
    phase = np.angle(f)
    residual = log_amp - cv2.blur(log_amp, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(residual + 1j * phase))) ** 2
    sal = cv2.GaussianBlur(sal.astype(np.float32), (9, 9), 2.5)
    total = float(sal.sum())
    if total <= 0:
        return None
    ys, xs = np.mgrid[0:64, 0:64]
    return float((sal * xs).sum() / total / 63), float((sal * ys).sum() / total / 63)


def analyze_quality(bgr: np.ndarray, face_boxes: Optional[list] = None) -> QualityResult:
    """bgr: analysis image (any size; resized internally). face_boxes: normalized (x,y,w,h)."""
    h, w = bgr.shape[:2]
    s = ANALYSIS_SIZE / max(h, w)
    if s < 1:
        bgr = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    global_var, tile_var = tiled_sharpness(gray)
    sharp = sharpness_score_from_var(tile_var)

    lum = gray.astype(np.float32) / 255.0
    brightness = float(lum.mean())
    hi = float((gray >= 250).mean())
    lo = float((gray <= 5).mean())
    # Exposure: penalize mean far from mid-tones and heavy clipping. Dark/bright scenes
    # (reception lighting, snow) are penalized gently, never excluded.
    exposure = 1.0 - min(1.0, abs(brightness - 0.48) / 0.45) * 0.6 - min(0.4, hi * 3) - min(0.4, lo * 2)
    exposure = float(min(1.0, max(0.0, exposure)))

    contrast_raw = float(lum.std())
    contrast = _scale(contrast_raw, 0.06, 0.22)

    sigma = estimate_noise(gray)
    noise = 1.0 - _scale(sigma, 1.5, 8.0)

    colorf = colorfulness(bgr)

    sal_center = None if face_boxes else spectral_saliency_center(gray)
    comp, comp_info = composition_score(face_boxes or [], sal_center)

    technical = 0.40 * sharp + 0.25 * exposure + 0.10 * contrast + 0.10 * noise + 0.15 * comp
    details = {
        "laplacian_var_global": round(global_var, 2),
        "laplacian_var_p90_tile": round(tile_var, 2),
        "noise_sigma": round(sigma, 3),
        "contrast_std": round(contrast_raw, 4),
        "colorfulness_raw": round(colorf, 2),
        "composition": comp_info,
        "version": QUALITY_VERSION,
    }
    return QualityResult(
        sharpness=round(sharp, 4),
        exposure=round(exposure, 4),
        brightness=round(brightness, 4),
        highlights_clipped=round(hi, 4),
        shadows_clipped=round(lo, 4),
        contrast=round(contrast, 4),
        noise=round(noise, 4),
        colorfulness=round(_scale(colorf, 10, 90), 4),
        composition=round(comp, 4),
        technical=round(float(technical), 4),
        details=details,
    )


def quality_issues(q: dict) -> list[str]:
    """Human-readable issue codes for the review queue."""
    issues = []
    if q.get("sharpness") is not None and q["sharpness"] < 0.25:
        issues.append("blurry")
    if q.get("exposure") is not None and q["exposure"] < 0.35:
        issues.append("exposure")
    if q.get("noise") is not None and q["noise"] < 0.3:
        issues.append("noisy")
    if q.get("composition") is not None and q["composition"] < 0.3:
        issues.append("weak_composition")
    return issues
