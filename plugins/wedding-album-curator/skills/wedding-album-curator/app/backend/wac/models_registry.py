"""Registry of downloadable local models.

Nothing is downloaded automatically: `download()` is only called from an explicit,
user-approved API request. Every file is verified against a pinned SHA-256.
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import httpx

from . import config


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    purpose: str
    filename: str
    url: str
    sha256: str
    size_bytes: int
    license: str
    license_url: str
    required_for: str


MODELS: dict[str, ModelSpec] = {
    m.id: m
    for m in [
        ModelSpec(
            id="yunet",
            name="YuNet face detector (OpenCV Zoo, 2023mar)",
            purpose="Detects faces and 5 facial landmarks.",
            filename="face_detection_yunet_2023mar.onnx",
            url="https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
            sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
            size_bytes=232_589,
            license="MIT",
            license_url="https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet",
            required_for="People discovery",
        ),
        ModelSpec(
            id="sface",
            name="SFace face recognition (OpenCV Zoo, 2021dec)",
            purpose="Computes a 128-number face descriptor used to group recurring people. Stored only locally.",
            filename="face_recognition_sface_2021dec.onnx",
            url="https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
            sha256="0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
            size_bytes=38_696_353,
            license="Apache-2.0",
            license_url="https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface",
            required_for="People discovery",
        ),
        ModelSpec(
            id="face_landmarker",
            name="MediaPipe Face Landmarker (float16 v1)",
            purpose="Estimates eye-blink scores to flag closed eyes.",
            filename="face_landmarker.task",
            url="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
            sha256="64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
            size_bytes=3_758_596,
            license="Apache-2.0",
            license_url="https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker",
            required_for="Closed-eye detection",
        ),
        ModelSpec(
            id="clip_vit_b32",
            name="OpenCLIP ViT-B/32 (LAION-2B s34B b79K)",
            purpose="Image embeddings for visual similarity, moment classification and preference learning.",
            filename="clip_vit_b32_laion2b_s34b_b79k.safetensors",
            url="https://huggingface.co/laion/CLIP-ViT-B-32-laion2B-s34B-b79K/resolve/main/open_clip_model.safetensors",
            sha256="ac4f8c4b88af6d963118cbf40ad93176d092abbedfcb752601ae1866352656e6",
            size_bytes=605_143_316,
            license="MIT",
            license_url="https://huggingface.co/laion/CLIP-ViT-B-32-laion2B-s34B-b79K",
            required_for="Similarity, moments, preference learning",
        ),
    ]
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_path(model_id: str) -> Path:
    return config.models_dir() / MODELS[model_id].filename


def is_installed(model_id: str) -> bool:
    p = model_path(model_id)
    return p.exists() and p.stat().st_size == MODELS[model_id].size_bytes


class DownloadManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.progress: dict[str, dict] = {}

    def status(self) -> list[dict]:
        out = []
        for m in MODELS.values():
            d = asdict(m)
            d["installed"] = is_installed(m.id)
            prog = self.progress.get(m.id)
            # once installed, a stale in-flight/error state is irrelevant
            d["download"] = None if d["installed"] and (prog or {}).get("state") != "done" else prog
            out.append(d)
        return out

    def start(self, model_ids: list[str]) -> None:
        for mid in model_ids:
            if mid not in MODELS:
                raise KeyError(mid)
        for mid in model_ids:
            with self._lock:
                cur = self.progress.get(mid)
                if cur and cur.get("state") == "downloading":
                    continue
                if is_installed(mid):
                    continue
                self.progress[mid] = {"state": "downloading", "received": 0, "total": MODELS[mid].size_bytes}
            threading.Thread(target=self._download, args=(mid,), daemon=True).start()

    MAX_ATTEMPTS = 8
    STALL_TIMEOUT_S = 20

    def _download(self, mid: str) -> None:
        """Download with automatic resume: a stalled or dropped connection is retried with an
        HTTP Range request from the bytes already received, then the whole file is verified."""
        spec = MODELS[mid]
        dest = model_path(mid)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.unlink(missing_ok=True)
        timeout = httpx.Timeout(30, read=self.STALL_TIMEOUT_S)
        last_error = ""
        try:
            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                have = tmp.stat().st_size if tmp.exists() else 0
                if have >= spec.size_bytes:
                    break
                headers = {"Range": f"bytes={have}-"} if have else {}
                try:
                    with httpx.stream("GET", spec.url, headers=headers, follow_redirects=True, timeout=timeout) as r:
                        r.raise_for_status()
                        if have and r.status_code != 206:  # server ignored Range: start over
                            have = 0
                        with open(tmp, "ab" if have else "wb") as f:
                            for chunk in r.iter_bytes(1 << 16):
                                f.write(chunk)
                                have += len(chunk)
                                self.progress[mid] = {"state": "downloading", "received": have,
                                                      "total": spec.size_bytes, "attempt": attempt}
                except (httpx.TransportError, httpx.HTTPStatusError) as e:
                    last_error = f"{type(e).__name__}: {e}"
                    time.sleep(min(2 ** attempt, 20))
                    continue
            else:
                raise RuntimeError(f"download kept failing after {self.MAX_ATTEMPTS} attempts ({last_error[:150]})")
            digest = sha256_of(tmp)
            if digest != spec.sha256:
                raise RuntimeError(f"checksum mismatch (got {digest[:12]}…)")
            tmp.replace(dest)
            self.progress[mid] = {"state": "done", "received": spec.size_bytes, "total": spec.size_bytes}
        except Exception as e:  # network errors, checksum errors
            tmp.unlink(missing_ok=True)
            if is_installed(mid):  # installed by other means meanwhile
                self.progress[mid] = {"state": "done", "received": spec.size_bytes, "total": spec.size_bytes}
            else:
                self.progress[mid] = {"state": "error", "error": str(e)[:300]}

    def delete(self, model_id: str) -> None:
        model_path(model_id).unlink(missing_ok=True)
        self.progress.pop(model_id, None)


downloads = DownloadManager()


def require(model_id: str) -> Optional[Path]:
    """Return the model path if installed, else None (callers degrade gracefully)."""
    return model_path(model_id) if is_installed(model_id) else None
