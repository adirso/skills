"""Vision provider abstraction.

The core computer-vision pipeline (faces, quality, embeddings) always runs locally.
A VisionProvider adds optional *semantic* analysis (moment category, emotional
significance, short factual caption) using a vision-language model.

Results are cached by (content hash, provider, model, prompt version, config hash), so
switching providers never loses earlier results, and re-running never re-pays for them.
Cloud providers refuse to run without a recorded, explicit consent.
"""
from __future__ import annotations

import abc
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from ..db import ProjectDB
from ..events import CATEGORY_LIST

PROMPT_VERSION = "v1"

ISSUE_CODES = ["closed_eyes", "looking_away", "motion_blur", "obstructed_face", "awkward_crop", "none"]

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORY_LIST},
        "category_confidence": {"type": "number"},
        "emotional_significance": {"type": "number"},
        "caption": {"type": "string"},
        "people_count": {"type": "integer"},
        "issues": {"type": "array", "items": {"type": "string", "enum": ISSUE_CODES}},
    },
    "required": ["category", "category_confidence", "emotional_significance", "caption", "people_count", "issues"],
    "additionalProperties": False,
}

PROMPT = (
    "You are helping a newly married couple choose photographs for their wedding album.\n"
    "Analyze this single wedding photograph and answer with JSON only.\n"
    f"- category: the wedding moment, one of: {', '.join(CATEGORY_LIST)}.\n"
    "- category_confidence: 0 to 1.\n"
    "- emotional_significance: 0 to 1, how meaningful this moment is likely to be for the couple "
    "(e.g. vows, first kiss, emotional reactions, laughter), based only on what is visible.\n"
    "- caption: one short, neutral, factual sentence describing what happens in the photo.\n"
    "- people_count: number of clearly visible people.\n"
    "- issues: visible technical problems among the allowed codes, or [\"none\"].\n"
    "Rules: do not comment on anyone's attractiveness, body, age, ethnicity or identity; "
    "do not guess names or family relationships; describe only what is visible."
)

CLOUD_WARNING = (
    "Using Claude may consume your Claude Code usage allowance or incur additional charges "
    "depending on your account and configuration. Images sent for analysis will be processed in the cloud."
)
CLOUD_WARNING_VERSION = 1


@dataclass
class ImageInput:
    photo_id: int
    content_hash: str
    jpeg_bytes: bytes
    width: int
    height: int


@dataclass
class ImageAnalysis:
    category: str
    category_confidence: float
    emotional_significance: float
    caption: str
    people_count: int
    issues: list
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    cost_basis: str = "unknown"
    model: Optional[str] = None

    def result_json(self) -> str:
        d = asdict(self)
        for k in ("input_tokens", "output_tokens", "cost_usd", "cost_basis", "model"):
            d.pop(k)
        return json.dumps(d)


@dataclass
class ProviderCapabilities:
    id: str
    name: str
    is_cloud: bool
    requires_consent: bool
    available: bool
    status: str
    models: list = field(default_factory=list)
    cost_note: str = ""
    max_concurrency: int = 1


class ProviderError(Exception):
    pass


class ConsentRequired(ProviderError):
    pass


class BudgetExceeded(ProviderError):
    pass


def normalize(raw: dict) -> dict:
    """Validate and clamp a model's JSON answer (model output is untrusted too)."""
    cat = raw.get("category")
    if cat not in CATEGORY_LIST:
        cat = "other"

    def clamp(v, default=0.0):
        try:
            return float(min(1.0, max(0.0, float(v))))
        except (TypeError, ValueError):
            return default

    issues = sorted({i for i in (raw.get("issues") or []) if i in ISSUE_CODES and i != "none"})
    try:
        people = max(0, min(500, int(raw.get("people_count") or 0)))
    except (TypeError, ValueError):
        people = 0
    caption = str(raw.get("caption") or "")[:300]
    return {
        "category": cat,
        "category_confidence": clamp(raw.get("category_confidence")),
        "emotional_significance": clamp(raw.get("emotional_significance")),
        "caption": caption,
        "people_count": people,
        "issues": issues,
    }


class VisionProvider(abc.ABC):
    id: str = "base"
    is_cloud: bool = False

    def __init__(self, model: str, options: Optional[dict] = None):
        self.model = model
        self.options = options or {}

    @abc.abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @abc.abstractmethod
    def analyze_image(self, inp: ImageInput) -> ImageAnalysis: ...

    def analyze_batch(self, inputs: list[ImageInput]) -> list[ImageAnalysis]:
        return [self.analyze_image(i) for i in inputs]

    def config_hash(self) -> str:
        cfg = {k: v for k, v in sorted(self.options.items()) if k in ("image_size", "effort")}
        return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]

    def estimate(self, n_images: int) -> dict:
        return {"images": n_images, "cost_usd_typical": None, "cost_usd_max": None, "basis": "not applicable"}


# ---------------- consent & cache helpers ----------------

def record_consent(db: ProjectDB, provider_id: str, accepted: bool) -> dict:
    consents = db.get_setting("cloud_consent", {})
    if accepted:
        consents[provider_id] = {"accepted_at": time.time(), "warning_version": CLOUD_WARNING_VERSION, "warning": CLOUD_WARNING}
    else:
        consents.pop(provider_id, None)
    db.set_setting("cloud_consent", consents)
    return consents


def has_consent(db: ProjectDB, provider_id: str) -> bool:
    c = db.get_setting("cloud_consent", {}).get(provider_id)
    return bool(c and c.get("warning_version") == CLOUD_WARNING_VERSION)


def require_consent(db: ProjectDB, provider: VisionProvider) -> None:
    if provider.is_cloud and not has_consent(db, provider.id):
        raise ConsentRequired(
            f"Explicit consent is required before photos are sent to {provider.id}. Nothing was uploaded."
        )


def cache_get(db: ProjectDB, provider: VisionProvider, content_hash: str) -> Optional[dict]:
    with db.connect() as con:
        row = con.execute(
            "SELECT result FROM ai_cache WHERE content_hash=? AND provider=? AND model=? AND prompt_version=? AND config_hash=?",
            (content_hash, provider.id, provider.model, PROMPT_VERSION, provider.config_hash()),
        ).fetchone()
    return json.loads(row["result"]) if row else None


def cache_put(db: ProjectDB, provider: VisionProvider, content_hash: str, analysis: ImageAnalysis, photo_id: int) -> None:
    with db.tx() as con:
        con.execute(
            "INSERT OR REPLACE INTO ai_cache(content_hash, provider, model, prompt_version, config_hash, result, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (content_hash, provider.id, provider.model, PROMPT_VERSION, provider.config_hash(), analysis.result_json(), time.time()),
        )
        if analysis.input_tokens is not None or analysis.cost_usd is not None:
            con.execute(
                "INSERT INTO usage_log(provider, model, photo_id, input_tokens, output_tokens, cost_usd, cost_basis, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (provider.id, analysis.model or provider.model, photo_id, analysis.input_tokens, analysis.output_tokens,
                 analysis.cost_usd, analysis.cost_basis, time.time()),
            )


def spent_usd(db: ProjectDB, provider_id: str) -> float:
    with db.connect() as con:
        v = con.execute("SELECT COALESCE(SUM(cost_usd),0) FROM usage_log WHERE provider=?", (provider_id,)).fetchone()[0]
    return float(v or 0.0)
