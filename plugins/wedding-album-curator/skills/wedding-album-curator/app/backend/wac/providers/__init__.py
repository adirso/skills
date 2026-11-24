from __future__ import annotations

from typing import Callable, Optional

from .anthropic_api import AnthropicAPIProvider
from .base import VisionProvider
from .claude_code import ClaudeCodeProvider
from .ollama import OllamaProvider

PROVIDER_IDS = ["none", "ollama", "anthropic_api", "claude_code"]


def get_provider(provider_id: str, model: str = "", options: Optional[dict] = None,
                 budget_check: Optional[Callable[[float], None]] = None) -> Optional[VisionProvider]:
    if provider_id == "ollama":
        return OllamaProvider(model or "qwen3-vl:8b-instruct", options)
    if provider_id == "anthropic_api":
        return AnthropicAPIProvider(model or "claude-opus-5-5", options, budget_check=budget_check)
    if provider_id == "claude_code":
        return ClaudeCodeProvider(model or "", options)
    if provider_id == "none":
        return None
    raise ValueError(f"unknown provider {provider_id}")
