"""Anthropic API list prices (USD per million tokens).

Source: Anthropic first-party API pricing as cached in Anthropic's claude-api reference
on 2026-11-03. Prices change; always verify at https://www.anthropic.com/pricing before
relying on an estimate. Estimates are not bills; actual cost is computed from the token
usage the API reports for each request.
"""
from __future__ import annotations

import math

PRICES_AS_OF = "2026-11-03"
PRICING_URL = "https://www.anthropic.com/pricing"

# model id -> (input $/MTok, output $/MTok)
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    # fallback targets that may serve a request when server-side fallbacks are enabled
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
}

SELECTABLE_MODELS = [
    {"id": "claude-opus-5-5", "label": "Claude Opus 5.5", "note": "Most capable of the three; highest cost."},
    {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "note": "Strong and cheaper."},
    {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5", "note": "Fastest and by far the cheapest."},
]

PROMPT_TOKENS = 450  # instructions + JSON schema, approximate
TYPICAL_OUTPUT_TOKENS = 350  # includes brief adaptive thinking at low effort, approximate
MAX_OUTPUT_TOKENS = 2000  # hard cap per request (max_tokens)


def image_tokens(width: int, height: int) -> int:
    """Vision inputs are tokenized at roughly one token per 28x28 pixel patch."""
    return math.ceil(width / 28) * math.ceil(height / 28)


def cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    p = PRICES.get(model)
    if not p:
        return None
    return (input_tokens * p[0] + output_tokens * p[1]) / 1_000_000


def estimate_per_image(model: str, width: int, height: int) -> tuple[float, float]:
    inp = image_tokens(width, height) + PROMPT_TOKENS
    typical = cost(model, inp, TYPICAL_OUTPUT_TOKENS) or 0.0
    # 25% safety margin on input because the image-token formula is approximate
    worst = cost(model, int(inp * 1.25), MAX_OUTPUT_TOKENS) or 0.0
    return typical, worst
