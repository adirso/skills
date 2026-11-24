"""Local vision-language analysis through an Ollama server on this computer."""
from __future__ import annotations

import base64
import json
import os
from typing import Iterator, Optional

import httpx

from .base import (ANALYSIS_SCHEMA, PROMPT, ImageAnalysis, ImageInput, ProviderCapabilities, ProviderError,
                   VisionProvider, normalize)

OLLAMA_URL = os.environ.get("WAC_OLLAMA_URL", "http://127.0.0.1:11434")


def _local_only(url: str) -> str:
    host = httpx.URL(url).host
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ProviderError("For privacy, the Ollama URL must point to this computer (localhost).")
    return url


def server_status() -> dict:
    try:
        r = httpx.get(f"{_local_only(OLLAMA_URL)}/api/version", timeout=2)
        r.raise_for_status()
        return {"running": True, "version": r.json().get("version")}
    except Exception as e:
        return {"running": False, "error": str(e)[:200]}


def list_models() -> list[dict]:
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
    except Exception:
        return []
    out = []
    for m in r.json().get("models", []):
        name = m.get("name")
        caps: list = []
        try:
            s = httpx.post(f"{OLLAMA_URL}/api/show", json={"model": name}, timeout=10)
            caps = s.json().get("capabilities", []) if s.status_code == 200 else []
        except Exception:
            pass
        out.append({"name": name, "size_gb": round((m.get("size") or 0) / 1e9, 1), "vision": "vision" in caps})
    return out


def pull(model: str) -> Iterator[dict]:
    """Stream download progress. Only called after explicit user approval."""
    with httpx.stream("POST", f"{OLLAMA_URL}/api/pull", json={"model": model, "stream": True}, timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


class OllamaProvider(VisionProvider):
    id = "ollama"
    is_cloud = False

    def capabilities(self) -> ProviderCapabilities:
        st = server_status()
        models = list_models() if st["running"] else []
        vision = [m["name"] for m in models if m["vision"]]
        ok = st["running"] and self.model in vision
        status = ("ready" if ok else
                  "Ollama is not running. Install it from ollama.com and start it." if not st["running"] else
                  f"Model {self.model} is not installed (or has no vision support).")
        return ProviderCapabilities(
            id=self.id, name="Local AI (Ollama)", is_cloud=False, requires_consent=False, available=ok,
            status=status, models=vision, cost_note="Free; runs on this computer.", max_concurrency=1,
        )

    def analyze_image(self, inp: ImageInput) -> ImageAnalysis:
        body = {
            "model": self.model,
            "stream": False,
            "format": ANALYSIS_SCHEMA,
            "options": {"temperature": 0},
            "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(inp.jpeg_bytes).decode()]}],
        }
        try:
            r = httpx.post(f"{_local_only(OLLAMA_URL)}/api/chat", json=body, timeout=300)
            if r.status_code >= 400:
                try:
                    msg = r.json().get("error", r.text)
                except ValueError:
                    msg = r.text
                raise ProviderError(f"Ollama could not run {self.model}: {str(msg)[:300]}")
            data = r.json()
            raw = json.loads(data["message"]["content"])
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
            raise ProviderError(f"Ollama analysis failed: {e}") from e
        n = normalize(raw)
        return ImageAnalysis(**n, input_tokens=data.get("prompt_eval_count"), output_tokens=data.get("eval_count"),
                             cost_usd=0.0, cost_basis="local", model=self.model)


def model_for_options(options: Optional[dict]) -> str:
    return (options or {}).get("model") or "qwen3-vl:8b-instruct"
