"""Claude via the Anthropic API (separately billed, pay-per-token, your own API key).

- The API key is read from the local secret store (or ANTHROPIC_API_KEY); it is never
  sent to the browser.
- Photos are downscaled (default 1024 px long edge) before upload.
- A spending limit is enforced by this application: before every request it checks that
  the recorded spend plus the worst-case cost of that request stays within the limit.
  This is an application-side guard, not a limit enforced by Anthropic's billing system.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Optional

from .. import secrets
from .base import (ANALYSIS_SCHEMA, PROMPT, BudgetExceeded, ImageAnalysis, ImageInput, ProviderCapabilities,
                   ProviderError, VisionProvider, normalize)
from . import pricing

FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicAPIProvider(VisionProvider):
    id = "anthropic_api"
    is_cloud = True

    def __init__(self, model: str, options: Optional[dict] = None, budget_check=None):
        super().__init__(model or "claude-opus-5-5", options)
        self.budget_check = budget_check  # callable(worst_case_usd) -> None, raises BudgetExceeded
        self._client = None

    def _client_or_raise(self):
        if self._client is None:
            key = secrets.get_anthropic_key()
            if not key:
                raise ProviderError("No Anthropic API key configured.")
            try:
                import anthropic
            except ImportError as e:
                raise ProviderError("The 'anthropic' package is not installed (pip install '.[cloud]').") from e
            self._client = anthropic.Anthropic(api_key=key, max_retries=4, timeout=120)
        return self._client

    def capabilities(self) -> ProviderCapabilities:
        has_key = bool(secrets.get_anthropic_key())
        return ProviderCapabilities(
            id=self.id, name="Claude API (Anthropic)", is_cloud=True, requires_consent=True,
            available=has_key, status="ready" if has_key else "Add an Anthropic API key to enable.",
            models=pricing.SELECTABLE_MODELS,
            cost_note=f"Billed per token by Anthropic to your API account. Prices as of {pricing.PRICES_AS_OF}; verify at {pricing.PRICING_URL}.",
            max_concurrency=3,
        )

    def estimate(self, n_images: int, width: int = 1024, height: int = 683) -> dict:
        typ, worst = pricing.estimate_per_image(self.model, width, height)
        return {
            "images": n_images,
            "model": self.model,
            "image_tokens_each": pricing.image_tokens(width, height),
            "cost_usd_typical": round(typ * n_images, 2),
            "cost_usd_max": round(worst * n_images, 2),
            "basis": (f"Estimate from list prices as of {pricing.PRICES_AS_OF}, ~{pricing.TYPICAL_OUTPUT_TOKENS} "
                      f"output tokens typical, {pricing.MAX_OUTPUT_TOKENS} max per photo. Cached results are free."),
        }

    def analyze_image(self, inp: ImageInput) -> ImageAnalysis:
        import anthropic

        client = self._client_or_raise()
        _, worst = pricing.estimate_per_image(self.model, inp.width, inp.height)
        if self.budget_check:
            self.budget_check(worst)
        kwargs = dict(
            model=self.model,
            max_tokens=pricing.MAX_OUTPUT_TOKENS,
            output_config={"effort": self.options.get("effort", "low"),
                           "format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                  "data": base64.standard_b64encode(inp.jpeg_bytes).decode()}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
        )
        attempt = 0
        while True:
            try:
                if self.model in FALLBACK_MODELS:
                    resp = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
                else:
                    resp = client.messages.create(**kwargs)
                break
            except anthropic.RateLimitError as e:
                attempt += 1
                if attempt > 5:
                    raise ProviderError("Rate limited repeatedly by the Anthropic API; try again later.") from e
                time.sleep(min(60, int(e.response.headers.get("retry-after", "10") or 10)))
            except anthropic.AuthenticationError as e:
                raise ProviderError("The Anthropic API key was rejected.") from e
            except anthropic.BadRequestError as e:
                raise ProviderError(f"The Anthropic API rejected the request: {e.message}") from e
            except anthropic.APIStatusError as e:
                raise ProviderError(f"Anthropic API error {e.status_code}") from e
            except anthropic.APIConnectionError as e:
                raise ProviderError("Could not reach the Anthropic API.") from e

        served_model = getattr(resp, "model", self.model) or self.model
        usage = resp.usage
        in_tok = (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        out_tok = usage.output_tokens or 0
        cost = pricing.cost(served_model, in_tok, out_tok)
        if cost is None:  # unknown fallback model: charge the requested model's price as an approximation
            cost = pricing.cost(self.model, in_tok, out_tok)
        if resp.stop_reason == "refusal":
            raise ProviderError("Claude declined to analyze this photo.")
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError("Claude returned an unparseable answer.") from e
        return ImageAnalysis(**normalize(raw), input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
                             cost_basis="api_usage", model=served_model)
