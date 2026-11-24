"""Local face detection (YuNet), face descriptors (SFace) and eye state (MediaPipe).

All processing is on-device. Face descriptors are biometric data: they are stored only
in the local project database and can be deleted from the Privacy screen.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from . import models_registry as mr

FACES_VERSION = 1
DETECT_SIZE = 1600
MIN_FACE_PX = 24
DET_THRESHOLD = 0.8
EYES_MIN_FACE_PX = 70
EYES_CLOSED_THRESHOLD = 0.6


@dataclass
class FaceResult:
    box: tuple[float, float, float, float]  # normalized x, y, w, h
    det_score: float
    size_px: float  # face width in pixels at full resolution
    landmarks: list[list[float]]  # 5 points, normalized
    embedding: Optional[np.ndarray]
    sharpness: float
    frontal: float
    edge_cut: bool
    blink_left: Optional[float] = None
    blink_right: Optional[float] = None
    eyes_closed: Optional[bool] = None
    eyes_reliable: bool = False
    landmarker_found: Optional[bool] = None
    extra: dict = field(default_factory=dict)


class FaceAnalyzer:
    """Not thread-safe; use `get_analyzer()` for a per-thread instance."""

    def __init__(self) -> None:
        det = mr.require("yunet")
        rec = mr.require("sface")
        if not det or not rec:
            raise RuntimeError("face models not installed")
        self.detector = cv2.FaceDetectorYN.create(str(det), "", (320, 320), DET_THRESHOLD, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(rec), "")
        self.landmarker = None
        lm = mr.require("face_landmarker")
        if lm:
            try:
                from mediapipe.tasks.python import BaseOptions, vision

                opts = vision.FaceLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(lm)),
                    num_faces=1,
                    output_face_blendshapes=True,
                    min_face_detection_confidence=0.4,
                )
                self.landmarker = vision.FaceLandmarker.create_from_options(opts)
            except Exception:  # MediaPipe missing or incompatible: eyes stay "unknown"
                self.landmarker = None

    def analyze(self, bgr: np.ndarray, full_width: int) -> list[FaceResult]:
        h, w = bgr.shape[:2]
        scale = DETECT_SIZE / max(h, w)
        img = bgr
        if scale < 1:
            img = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        ih, iw = img.shape[:2]
        self.detector.setInputSize((iw, ih))
        _, faces = self.detector.detect(img)
        if faces is None:
            return []
        px_scale = full_width / iw
        results = []
        for row in faces:
            x, y, fw, fh = [float(v) for v in row[:4]]
            score = float(row[14])
            if fw < MIN_FACE_PX or fh < MIN_FACE_PX:
                continue
            lms = np.array(row[4:14], dtype=np.float32).reshape(5, 2)
            # Descriptor
            try:
                aligned = self.recognizer.alignCrop(img, row)
                feat = self.recognizer.feature(aligned).flatten().astype(np.float32)
                n = np.linalg.norm(feat)
                emb = feat / n if n > 0 else None
            except cv2.error:
                aligned, emb = None, None
            # Face sharpness on a normalized crop
            x0, y0 = max(0, int(x)), max(0, int(y))
            x1, y1 = min(iw, int(x + fw)), min(ih, int(y + fh))
            crop = img[y0:y1, x0:x1]
            sharp = 0.0
            if crop.size:
                g = cv2.cvtColor(cv2.resize(crop, (128, 128)), cv2.COLOR_BGR2GRAY)
                v = float(cv2.Laplacian(g, cv2.CV_64F).var())
                sharp = float(min(1.0, max(0.0, (np.log10(max(v, 1e-3)) - 1.3) / 1.3)))
            # Frontalness: nose horizontal offset from eye midpoint relative to eye distance
            re, le, nose = lms[0], lms[1], lms[2]
            eye_dist = float(np.linalg.norm(le - re)) or 1.0
            yaw = abs(float(nose[0] - (re[0] + le[0]) / 2)) / eye_dist
            frontal = float(max(0.0, 1.0 - yaw / 0.6))
            edge_cut = x < 2 or y < 2 or x + fw > iw - 2 or y + fh > ih - 2
            fr = FaceResult(
                box=(x / iw, y / ih, fw / iw, fh / ih),
                det_score=score,
                size_px=fw * px_scale,
                landmarks=[[float(p[0] / iw), float(p[1] / ih)] for p in lms],
                embedding=emb,
                sharpness=round(sharp, 4),
                frontal=round(frontal, 4),
                edge_cut=bool(edge_cut),
            )
            if self.landmarker is not None:
                self._eyes(img, (x, y, fw, fh), fr)
            results.append(fr)
        return results

    def _eyes(self, img: np.ndarray, box: tuple, fr: FaceResult) -> None:
        import mediapipe as mp

        x, y, fw, fh = box
        if fw < EYES_MIN_FACE_PX:
            return
        ih, iw = img.shape[:2]
        m = 0.45
        x0, y0 = max(0, int(x - fw * m)), max(0, int(y - fh * m))
        x1, y1 = min(iw, int(x + fw * (1 + m))), min(ih, int(y + fh * (1 + m)))
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            return
        if max(crop.shape[:2]) < 256:
            s = 256 / max(crop.shape[:2])
            crop = cv2.resize(crop, (int(crop.shape[1] * s), int(crop.shape[0] * s)), interpolation=cv2.INTER_CUBIC)
        rgb = np.ascontiguousarray(crop[:, :, ::-1])
        try:
            res = self.landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        except Exception:
            return
        if not res.face_blendshapes:
            fr.landmarker_found = False
            return
        fr.landmarker_found = True
        shapes = {c.category_name: float(c.score) for c in res.face_blendshapes[0]}
        bl, br = shapes.get("eyeBlinkLeft"), shapes.get("eyeBlinkRight")
        if bl is None or br is None:
            return
        fr.blink_left, fr.blink_right = round(bl, 3), round(br, 3)
        # Only call it reliable for reasonably large, roughly frontal faces.
        fr.eyes_reliable = fw >= 90 and fr.frontal >= 0.5
        fr.eyes_closed = bool(bl >= EYES_CLOSED_THRESHOLD and br >= EYES_CLOSED_THRESHOLD)


_local = threading.local()


def get_analyzer() -> Optional[FaceAnalyzer]:
    if not (mr.is_installed("yunet") and mr.is_installed("sface")):
        return None
    an = getattr(_local, "analyzer", None)
    if an is None:
        an = FaceAnalyzer()
        _local.analyzer = an
    return an


def reset_analyzers() -> None:
    _local.__dict__.clear()
