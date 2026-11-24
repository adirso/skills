"""Local image/text embeddings with OpenCLIP (optional; requires the `ml` extra and model approval)."""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np
from PIL import Image

from . import models_registry as mr

MODEL_NAME = "openclip-vit-b32-laion2b"
_lock = threading.Lock()
_state: dict = {}


def available() -> bool:
    if not mr.is_installed("clip_vit_b32"):
        return False
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401
    except Exception:
        return False
    return True


def device_name() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _load():
    if "model" in _state:
        return _state["model"], _state["preprocess"], _state["tokenizer"], _state["device"]
    import open_clip
    import torch

    dev = device_name()
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained=str(mr.model_path("clip_vit_b32")), device=dev
    )
    model.eval()
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    torch.set_grad_enabled(False)
    _state.update(model=model, preprocess=preprocess, tokenizer=tokenizer, device=dev)
    return model, preprocess, tokenizer, dev


def embed_images(images: list[Image.Image]) -> np.ndarray:
    import torch

    with _lock:
        model, preprocess, _, dev = _load()
        batch = torch.stack([preprocess(im.convert("RGB")) for im in images]).to(dev)
        with torch.inference_mode():
            feats = model.encode_image(batch).float()
        feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy().astype(np.float32)


def embed_texts(texts: list[str]) -> np.ndarray:
    import torch

    with _lock:
        model, _, tokenizer, dev = _load()
        tokens = tokenizer(texts).to(dev)
        with torch.inference_mode():
            feats = model.encode_text(tokens).float()
        feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy().astype(np.float32)


def logit_scale() -> float:
    with _lock:
        model, *_ = _load()
        try:
            return float(model.logit_scale.exp().item())
        except Exception:
            return 100.0


def unload() -> Optional[bool]:
    with _lock:
        _state.clear()
    return True
