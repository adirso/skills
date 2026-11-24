"""Wedding moment classification.

Signals combined:
- CLIP zero-shot similarity against several descriptive prompts per category.
- Timeline segmentation (gaps in EXIF capture time) used for gentle smoothing only;
  timestamps can be wrong (unsynced cameras), so they never override the image itself.
- Optional vision-language provider results (when the user ran one).
- User corrections always win and are never overwritten.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Optional

import numpy as np

from . import embeddings
from .db import ProjectDB, from_blob

CATEGORIES: dict[str, list[str]] = {
    "getting_ready": [
        "a bride getting her makeup and hair done before the wedding",
        "a bride putting on her wedding dress",
        "a groom getting dressed and adjusting his tie",
        "wedding preparations in a hotel room",
    ],
    "couple_portraits": [
        "a romantic portrait of a bride and groom posing together",
        "a newlywed couple posing for a photo shoot outdoors",
    ],
    "family_portraits": [
        "a formal group photo of a family posing with the bride and groom",
        "a bride posing with her parents",
    ],
    "friends": [
        "a group of friends posing and smiling at a wedding",
        "bridesmaids posing together",
        "groomsmen posing together",
    ],
    "ceremony": [
        "a wedding ceremony with seated guests watching",
        "a bride walking down the aisle",
        "a couple standing under a wedding canopy with an officiant",
        "a couple exchanging vows at the altar",
    ],
    "rings": [
        "a close-up photo of wedding rings",
        "placing a wedding ring on a finger",
    ],
    "first_kiss": [
        "a bride and groom kissing during the wedding ceremony",
    ],
    "first_dance": [
        "a bride and groom dancing together alone on the dance floor",
    ],
    "reception": [
        "guests sitting at decorated tables at a wedding reception dinner",
        "a wedding cake",
        "a person giving a toast speech at a wedding reception",
        "decorated wedding reception hall",
    ],
    "party_dancing": [
        "wedding guests dancing at a party",
        "a crowded dance floor with colorful party lights",
    ],
    "other": [
        "a landscape photo of a wedding venue",
        "a candid photo of a person",
    ],
}
CATEGORY_LIST = list(CATEGORIES)

# Which album allocation bucket each category counts towards.
BUCKETS: dict[str, list[str]] = {
    "getting_ready": ["getting_ready"],
    "couple": ["couple_portraits", "first_kiss", "rings"],
    "family_friends": ["family_portraits", "friends"],
    "ceremony": ["ceremony"],
    "reception_dancing": ["reception", "first_dance", "party_dancing"],
    "other": ["other"],
}
CATEGORY_TO_BUCKET = {c: b for b, cs in BUCKETS.items() for c in cs}

SEGMENT_GAP_S = 15 * 60
SMOOTHING = 0.35

_text_cache: dict[str, np.ndarray] = {}


def category_text_embeddings() -> np.ndarray:
    if "all" not in _text_cache:
        rows = []
        for cat in CATEGORY_LIST:
            e = embeddings.embed_texts([f"a wedding photo: {p}" for p in CATEGORIES[cat]])
            m = e.mean(axis=0)
            rows.append(m / np.linalg.norm(m))
        _text_cache["all"] = np.stack(rows)
    return _text_cache["all"]


def segment_timeline(taken: list[tuple[int, Optional[float]]], gap: float = SEGMENT_GAP_S) -> dict[int, int]:
    """Return photo_id -> segment index. Photos without timestamps get no segment."""
    timed = sorted((t, pid) for pid, t in taken if t is not None)
    seg: dict[int, int] = {}
    cur, last = 0, None
    for t, pid in timed:
        if last is not None and t - last > gap:
            cur += 1
        seg[pid] = cur
        last = t
    return seg


def classify_all(db: ProjectDB) -> dict:
    with db.connect() as con:
        photos = [dict(r) for r in con.execute("SELECT id, taken_ts FROM photos WHERE status='ok'")]
        embs = {r["photo_id"]: from_blob(r["vector"]) for r in con.execute("SELECT photo_id, vector FROM embeddings")}
        user_set = {r["photo_id"] for r in con.execute("SELECT photo_id FROM events WHERE source='user'")}
        vlm = {r["photo_id"]: dict(r) for r in con.execute("SELECT photo_id, category, confidence FROM events WHERE source='vlm'")}
    segments = segment_timeline([(p["id"], p["taken_ts"]) for p in photos])
    with db.tx() as con:
        con.executemany("UPDATE photos SET segment_id=? WHERE id=?", [(segments.get(p["id"]), p["id"]) for p in photos])

    if not embs or not embeddings.available():
        return {"classified": 0, "reason": "CLIP model not installed; moments not classified", "segments": len(set(segments.values()))}

    text = category_text_embeddings()
    scale = embeddings.logit_scale()
    probs: dict[int, np.ndarray] = {}
    for pid, e in embs.items():
        logits = scale * (text @ e)
        logits -= logits.max()
        p = np.exp(logits)
        probs[pid] = p / p.sum()
    seg_members: dict[int, list[int]] = defaultdict(list)
    for pid, s in segments.items():
        if pid in probs:
            seg_members[s].append(pid)
    seg_mean = {s: np.mean([probs[m] for m in ms], axis=0) for s, ms in seg_members.items()}

    rows = []
    for pid, p in probs.items():
        if pid in user_set or pid in vlm:
            continue
        s = segments.get(pid)
        q = (1 - SMOOTHING) * p + SMOOTHING * seg_mean[s] if s is not None and len(seg_members[s]) > 3 else p
        k = int(np.argmax(q))
        top = {CATEGORY_LIST[i]: round(float(q[i]), 3) for i in np.argsort(-q)[:3]}
        rows.append((pid, CATEGORY_LIST[k], float(q[k]), "clip", json.dumps(top)))
    with db.tx() as con:
        con.executemany(
            "INSERT INTO events(photo_id, category, confidence, source, scores) VALUES (?,?,?,?,?) "
            "ON CONFLICT(photo_id) DO UPDATE SET category=excluded.category, confidence=excluded.confidence, "
            "source=excluded.source, scores=excluded.scores WHERE events.source NOT IN ('user','vlm')",
            rows,
        )
    return {"classified": len(rows), "segments": len(seg_members)}


def set_user_category(db: ProjectDB, photo_ids: list[int], category: str) -> None:
    if category not in CATEGORIES:
        raise ValueError("unknown category")
    with db.tx() as con:
        con.executemany(
            "INSERT INTO events(photo_id, category, confidence, source) VALUES (?, ?, 1.0, 'user') "
            "ON CONFLICT(photo_id) DO UPDATE SET category=excluded.category, confidence=1.0, source='user'",
            [(pid, category) for pid in photo_ids],
        )
