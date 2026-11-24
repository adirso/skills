"""Hardware detection and local-model recommendations."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Optional

import psutil


def _run(cmd: list[str], timeout: float = 5) -> Optional[str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def detect() -> dict:
    info: dict = {
        "os": platform.system(),
        "os_version": platform.release(),
        "arch": platform.machine(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_cores": os.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        "gpus": [],
        "accelerator": "cpu",
        "torch": None,
    }
    if info["os"] == "Darwin":
        brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if brand:
            info["cpu"] = brand.strip()
        if info["arch"] == "arm64":
            # Apple Silicon: unified memory shared between CPU and GPU
            info["gpus"].append({"name": info["cpu"], "vendor": "Apple", "memory_gb": info["ram_gb"],
                                 "memory_note": "unified memory shared with the CPU", "api": "Metal"})
    if shutil.which("nvidia-smi"):
        out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        if out:
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 2:
                    try:
                        mem = round(float(parts[1]) / 1024, 1)
                    except ValueError:
                        mem = None
                    info["gpus"].append({"name": parts[0], "vendor": "NVIDIA", "memory_gb": mem, "api": "CUDA"})
    try:
        import torch

        t = {"version": torch.__version__, "cuda": torch.cuda.is_available(), "mps": torch.backends.mps.is_available()}
        info["torch"] = t
        info["accelerator"] = "cuda" if t["cuda"] else ("mps" if t["mps"] else "cpu")
    except Exception:
        info["torch"] = None
    return info


# Ollama vision models we recommend, smallest first. Sizes are approximate download sizes
# of the default quantization; RAM is a practical minimum for comfortable use.
OLLAMA_VISION_MODELS = [
    {"name": "qwen3-vl:2b-instruct", "download_gb": 1.9, "min_ram_gb": 8, "license": "Apache-2.0",
     "note": "Fastest. Basic scene recognition; descriptions can be generic."},
    {"name": "qwen3-vl:4b-instruct", "download_gb": 3.3, "min_ram_gb": 12, "license": "Apache-2.0",
     "note": "Good balance for laptops."},
    {"name": "qwen3-vl:8b-instruct", "download_gb": 6.2, "min_ram_gb": 16, "license": "Apache-2.0",
     "note": "Recommended when you have 16 GB+ of memory."},
    {"name": "qwen3-vl:30b-a3b-instruct", "download_gb": 20, "min_ram_gb": 36, "license": "Apache-2.0",
     "note": "Mixture-of-experts (about 3B active parameters): high quality, still reasonably fast on 36 GB+ machines."},
]
# Sizes verified against ollama.com/library/qwen3-vl/tags on 2026-11-23.


def recommend(info: dict) -> dict:
    ram = info.get("ram_gb") or 0
    acc = info.get("accelerator")
    fitting = [m for m in OLLAMA_VISION_MODELS if m["min_ram_gb"] <= ram]
    vlm = fitting[-1] if fitting else None
    if acc in ("mps", "cuda"):
        speed = "GPU acceleration available. Expect roughly 5–20 photos/second for core analysis (faces, quality, embeddings) and roughly 1–4 seconds per photo for an optional vision-language model."
    else:
        speed = "No supported GPU detected. Core analysis runs on the CPU (roughly 1–5 photos/second); a vision-language model will be slow (10+ seconds per photo) and is not recommended."
    if ram < 8:
        speed += " Less than 8 GB of RAM: keep other applications closed during analysis."
    return {
        "core_models": ["yunet", "sface", "face_landmarker", "clip_vit_b32"],
        "ollama_model": vlm["name"] if vlm and acc in ("mps", "cuda") else (fitting[0]["name"] if fitting else None),
        "ollama_candidates": OLLAMA_VISION_MODELS,
        "speed_estimate": speed,
        "note": "Speed figures are rough guidance, not measurements on your machine. The app shows measured throughput while analysis runs.",
    }
