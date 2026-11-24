"""Album recommendation engine.

Diversity-aware greedy selection (a maximal-marginal-relevance variant):

  base score   = weighted sum of separate, explainable components
                 (technical quality, face quality of important people, importance of the
                 people present, moment significance, learned preference, explicit ratings)
  marginal gain = base score adjusted for what is already in the album:
                 - penalty for near-duplicates already chosen (same similarity group)
                 - penalty for visual similarity to chosen photos (CLIP embeddings)
                 - soft penalty when a moment bucket already reached its allocation
                 - bonus for the first photos of important people not yet covered
                 - bonus for bride/groom photos while their coverage is below target

Rules that are never broken:
  - Photos the user selected (locked) are always included.
  - Photos the user rejected are never selected.
  - If there are not enough eligible photos, the shortfall is reported, not padded.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np

from . import preferences
from .db import ProjectDB, from_blob
from .events import BUCKETS, CATEGORY_TO_BUCKET

DEFAULT_ALLOCATIONS = {
    "getting_ready": 10,
    "couple": 20,
    "family_friends": 20,
    "ceremony": 20,
    "reception_dancing": 30,
    "other": 0,
}

DEFAULT_IMPORTANCE = {
    "bride": {"label": "Bride", "weight": 1.0, "order": 1},
    "groom": {"label": "Groom", "weight": 1.0, "order": 2},
    "family": {"label": "Immediate family", "weight": 0.7, "order": 3},
    "close_friends": {"label": "Close friends", "weight": 0.5, "order": 4},
    "other": {"label": "Other guests", "weight": 0.2, "order": 5},
    "low": {"label": "Low priority", "weight": 0.02, "order": 6},
}

MOMENT_WEIGHTS = {
    "first_kiss": 1.0, "first_dance": 0.9, "rings": 0.8, "ceremony": 0.8,
    "couple_portraits": 0.8, "family_portraits": 0.7, "getting_ready": 0.6,
    "friends": 0.6, "party_dancing": 0.55, "reception": 0.5, "other": 0.3,
}


@dataclass
class SelectionConfig:
    target: int = 500
    allocations: dict = field(default_factory=lambda: dict(DEFAULT_ALLOCATIONS))
    weights: dict = field(default_factory=lambda: {
        "technical": 0.30, "faces": 0.20, "people": 0.25, "moment": 0.10, "preference": 0.10, "rating": 0.05,
    })
    max_per_group: int = 1
    similarity_penalty: float = 0.35
    couple_coverage: float = 0.5
    allocation_overflow_penalty: float = 0.5

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "SelectionConfig":
        c = cls()
        if d:
            for k, v in d.items():
                if hasattr(c, k) and v is not None:
                    setattr(c, k, v)
        c.target = max(1, int(c.target))
        return c


@dataclass
class Candidate:
    id: int
    technical: float = 0.5
    sharpness: float = 0.5
    exposure: float = 0.5
    face_quality: Optional[float] = None
    persons: list = field(default_factory=list)  # person ids present
    person_weights: dict = field(default_factory=dict)  # person id -> weight
    has_bride: bool = False
    has_groom: bool = False
    couple_eyes_closed: bool = False
    category: str = "other"
    category_conf: float = 0.0
    group_id: Optional[int] = None
    group_size: int = 1
    embedding: Optional[np.ndarray] = None
    preference: Optional[float] = None
    favorite: bool = False
    rating: Optional[int] = None
    decision: Optional[str] = None
    ai_significance: Optional[float] = None


@dataclass
class Pick:
    id: int
    score: float
    bucket: str
    reasons: list
    components: dict


@dataclass
class SelectionResult:
    picks: list
    summary: dict


def base_components(c: Candidate) -> dict:
    people = 1.0
    for w in c.person_weights.values():
        people *= (1.0 - min(0.99, w))
    people = 1.0 - people if c.person_weights else 0.0
    moment = MOMENT_WEIGHTS.get(c.category, 0.3) * (0.6 + 0.4 * min(1.0, c.category_conf))
    if c.ai_significance is not None:
        moment = max(moment, c.ai_significance)
    rating = 1.0 if c.favorite else ((c.rating - 1) / 4 if c.rating else 0.0)
    return {
        "technical": c.technical,
        "faces": c.face_quality if c.face_quality is not None else 0.5,
        "people": people,
        "moment": moment,
        "preference": c.preference if c.preference is not None else 0.5,
        "rating": rating,
    }


def base_score(c: Candidate, cfg: SelectionConfig) -> tuple[float, dict]:
    comp = base_components(c)
    total_w = sum(cfg.weights.values()) or 1.0
    s = sum(cfg.weights.get(k, 0) * v for k, v in comp.items()) / total_w
    mult = 1.0
    if c.sharpness < 0.15:
        mult *= 0.6
    if c.couple_eyes_closed:
        mult *= 0.6
    comp["multiplier"] = mult
    return s * mult, comp


def explain(c: Candidate, comp: dict, locked: bool, person_names: dict) -> list[str]:
    if locked:
        return ["Selected by you (locked)"]
    r = []
    if c.has_bride and c.has_groom:
        r.append("Bride and groom together")
    elif c.has_bride:
        r.append("Features the bride")
    elif c.has_groom:
        r.append("Features the groom")
    named = [person_names[p] for p in c.persons if p in person_names and c.person_weights.get(p, 0) >= 0.5][:3]
    if named:
        r.append("Includes " + ", ".join(named))
    if c.category not in ("other",) and c.category_conf >= 0.3:
        r.append(f"Moment: {c.category.replace('_', ' ')}")
    if comp["technical"] >= 0.7:
        r.append("Strong technical quality")
    if c.face_quality is not None and c.face_quality >= 0.7:
        r.append("Clear, well-lit faces")
    if c.group_size > 1:
        r.append(f"Best of {c.group_size} similar shots")
    if c.favorite or (c.rating or 0) >= 4:
        r.append("You marked it as a favorite")
    elif c.preference is not None and c.preference >= 0.75:
        r.append("Similar to photos you liked")
    if comp.get("multiplier", 1) < 1:
        r.append("Included despite a possible issue — please review")
    return r or ["Adds variety to the album"]


def select(cands: list[Candidate], cfg: SelectionConfig, person_names: Optional[dict] = None,
           important_persons: Optional[set] = None) -> SelectionResult:
    person_names = person_names or {}
    important_persons = important_persons or set()
    t0 = time.time()
    locked = [c for c in cands if c.decision == "selected"]
    rejected = [c for c in cands if c.decision == "rejected"]
    pool = [c for c in cands if c.decision not in ("selected", "rejected")]

    alloc_total = sum(v for v in cfg.allocations.values() if v > 0) or 1
    bucket_target = {b: int(round(cfg.target * max(0, cfg.allocations.get(b, 0)) / alloc_total)) for b in BUCKETS}
    bucket_count = {b: 0 for b in BUCKETS}
    group_count: dict[int, int] = {}
    person_count: dict[int, int] = {}
    couple_count = 0

    picks: list[Pick] = []

    def register(c: Candidate) -> None:
        nonlocal couple_count
        b = CATEGORY_TO_BUCKET.get(c.category, "other")
        bucket_count[b] += 1
        if c.group_id is not None:
            group_count[c.group_id] = group_count.get(c.group_id, 0) + 1
        for p in c.persons:
            person_count[p] = person_count.get(p, 0) + 1
        if c.has_bride or c.has_groom:
            couple_count += 1

    for c in locked:
        s, comp = base_score(c, cfg)
        picks.append(Pick(c.id, round(s, 4), CATEGORY_TO_BUCKET.get(c.category, "other"), explain(c, comp, True, person_names), comp))
        register(c)

    slots = cfg.target - len(locked)
    n = len(pool)
    base = np.zeros(n)
    comps: list[dict] = []
    for i, c in enumerate(pool):
        s, comp = base_score(c, cfg)
        base[i] = s
        comps.append(comp)

    dim = next((c.embedding.shape[0] for c in cands if c.embedding is not None), 0)
    has_emb = np.array([c.embedding is not None for c in pool], dtype=bool)
    E = np.stack([c.embedding if c.embedding is not None else np.zeros(dim, np.float32) for c in pool]) if n and dim else None
    max_sim = np.zeros(n)
    if E is not None:
        for c in locked:
            if c.embedding is not None:
                max_sim = np.maximum(max_sim, E @ c.embedding)

    buckets = [CATEGORY_TO_BUCKET.get(c.category, "other") for c in pool]
    available = np.ones(n, dtype=bool)
    is_couple = np.array([c.has_bride or c.has_groom for c in pool], dtype=bool)
    person_index: dict[int, list[int]] = {}
    for i, c in enumerate(pool):
        for p in c.persons:
            person_index.setdefault(p, []).append(i)

    def coverage_bonus() -> np.ndarray:
        bonus = np.zeros(n)
        for p in important_persons:
            if person_count.get(p, 0) < 3:
                for i in person_index.get(p, []):
                    bonus[i] += 0.06
        return bonus

    cov = coverage_bonus()
    selected_n = len(locked)
    while slots > 0 and available.any():
        gain = base.copy()
        if E is not None:
            sim_pen = np.clip((max_sim - 0.80) / 0.20, 0, 1) * cfg.similarity_penalty
            gain -= np.where(has_emb, sim_pen, 0)
        for i in np.where(available)[0]:
            c = pool[i]
            if c.group_id is not None:
                gc = group_count.get(c.group_id, 0)
                if gc >= cfg.max_per_group:
                    gain[i] *= 0.25 ** (gc - cfg.max_per_group + 1)
            b = buckets[i]
            if bucket_count[b] >= bucket_target.get(b, 0):
                gain[i] *= cfg.allocation_overflow_penalty
        gain += cov
        if selected_n and couple_count / max(selected_n, 1) < cfg.couple_coverage:
            gain += np.where(is_couple, 0.08, 0.0)
        gain[~available] = -np.inf
        i = int(np.argmax(gain))
        if not np.isfinite(gain[i]):
            break
        c = pool[i]
        available[i] = False
        reasons = explain(c, comps[i], False, person_names)
        if c.persons and any(person_count.get(p, 0) == 0 for p in c.persons if p in important_persons):
            reasons.append("Improves coverage of important people")
        picks.append(Pick(c.id, round(float(gain[i]), 4), buckets[i], reasons, comps[i]))
        register(c)
        selected_n += 1
        slots -= 1
        if E is not None and c.embedding is not None:
            max_sim = np.maximum(max_sim, E @ c.embedding)
        if c.persons and any(p in important_persons for p in c.persons):
            cov = coverage_bonus()

    shortfall = max(0, cfg.target - len(picks))
    achieved = {b: 0 for b in BUCKETS}
    for p in picks:
        achieved[p.bucket] += 1
    notes = []
    if shortfall:
        notes.append(
            f"Only {len(picks)} photos could be selected: there are not enough eligible photos "
            f"(after excluding {len(rejected)} rejected photos and exact duplicates)."
        )
    if len(locked) > cfg.target:
        notes.append(f"You locked {len(locked)} photos, which is more than the target of {cfg.target}.")
    for b, t in bucket_target.items():
        if t and achieved[b] < t * 0.6:
            avail = sum(1 for c in cands if CATEGORY_TO_BUCKET.get(c.category, "other") == b and c.decision != "rejected")
            notes.append(f"'{b.replace('_', ' ')}' has {achieved[b]} photos vs. a suggested {t} ({avail} candidates available).")
    summary = {
        "target": cfg.target,
        "selected": len(picks),
        "locked": len(locked),
        "rejected_excluded": len(rejected),
        "eligible_pool": n,
        "shortfall": shortfall,
        "bucket_target": bucket_target,
        "bucket_achieved": achieved,
        "couple_share": round(couple_count / max(len(picks), 1), 3),
        "notes": notes,
        "elapsed_s": round(time.time() - t0, 3),
    }
    return SelectionResult(picks=picks, summary=summary)


# ---------------- DB integration ----------------

def importance_levels(db: ProjectDB) -> dict:
    levels = db.get_setting("importance_levels")
    return levels if levels else dict(DEFAULT_IMPORTANCE)


def person_weights(db: ProjectDB) -> tuple[dict[int, float], dict[int, str], dict[int, str]]:
    levels = importance_levels(db)
    weights, names, roles = {}, {}, {}
    with db.connect() as con:
        for p in con.execute("SELECT id, name, role, importance, hidden FROM persons"):
            key = p["role"] or p["importance"]
            weights[p["id"]] = 0.0 if p["hidden"] else float(levels.get(key, levels.get("other", {"weight": 0.2}))["weight"])
            if p["name"]:
                names[p["id"]] = p["name"]
            if p["role"]:
                roles[p["id"]] = p["role"]
                names.setdefault(p["id"], p["role"].capitalize())
    return weights, names, roles


def gather_candidates(db: ProjectDB) -> tuple[list[Candidate], dict, set]:
    weights, names, roles = person_weights(db)
    pref = preferences.build(db)
    cands: dict[int, Candidate] = {}
    with db.connect() as con:
        for r in con.execute(
            "SELECT p.id, p.group_id, q.technical, q.sharpness, q.exposure, e.category, e.confidence, "
            "u.decision, u.favorite, u.rating FROM photos p "
            "LEFT JOIN quality q ON q.photo_id=p.id LEFT JOIN events e ON e.photo_id=p.id "
            "LEFT JOIN user_state u ON u.photo_id=p.id "
            "WHERE p.status='ok' AND (p.duplicate_of IS NULL OR u.decision='selected')"
        ):
            cands[r["id"]] = Candidate(
                id=r["id"],
                technical=r["technical"] if r["technical"] is not None else 0.5,
                sharpness=r["sharpness"] if r["sharpness"] is not None else 0.5,
                exposure=r["exposure"] if r["exposure"] is not None else 0.5,
                category=r["category"] or "other",
                category_conf=r["confidence"] or 0.0,
                group_id=r["group_id"],
                decision=r["decision"],
                favorite=bool(r["favorite"]),
                rating=r["rating"],
            )
        sizes = {r["group_id"]: r["n"] for r in con.execute(
            "SELECT group_id, COUNT(*) n FROM photos WHERE group_id IS NOT NULL AND status='ok' GROUP BY group_id")}
        face_rows = con.execute(
            "SELECT photo_id, person_id, sharpness, frontal, eyes_closed, eyes_reliable FROM faces WHERE assignment!='ignored'"
        ).fetchall()
        for r in con.execute("SELECT photo_id, vector FROM embeddings"):
            if r["photo_id"] in cands:
                cands[r["photo_id"]].embedding = from_blob(r["vector"])
        ai_sig = {}
        src = db.get_setting("active_ai_result_source")
        if src:
            prov, _, model = src.partition(":")
            for r in con.execute(
                "SELECT p.id, a.result FROM photos p JOIN ai_cache a ON a.content_hash=p.sha256 "
                "WHERE a.provider=? AND a.model=?", (prov, model)
            ):
                try:
                    ai_sig[r["id"]] = float(json.loads(r["result"]).get("emotional_significance"))
                except Exception:
                    pass
    per_photo_faces: dict[int, list] = {}
    for f in face_rows:
        per_photo_faces.setdefault(f["photo_id"], []).append(f)
    for pid, c in cands.items():
        c.group_size = sizes.get(c.group_id, 1) if c.group_id is not None else 1
        c.preference = pref.scores.get(pid) if pref.method != "none" else None
        c.ai_significance = ai_sig.get(pid)
        fs = per_photo_faces.get(pid, [])
        persons = sorted({f["person_id"] for f in fs if f["person_id"] is not None})
        c.persons = persons
        c.person_weights = {p: weights.get(p, 0.2) for p in persons}
        c.has_bride = any(roles.get(p) == "bride" for p in persons)
        c.has_groom = any(roles.get(p) == "groom" for p in persons)
        key_faces = [f for f in fs if f["person_id"] is not None and weights.get(f["person_id"], 0) >= 0.5]
        use = key_faces or fs
        if use:
            vals = []
            for f in use:
                eyes = 0.5 if f["eyes_closed"] is None or not f["eyes_reliable"] else (0.0 if f["eyes_closed"] else 1.0)
                vals.append(0.4 * (f["sharpness"] or 0) + 0.3 * (f["frontal"] or 0) + 0.3 * eyes)
            c.face_quality = float(np.mean(vals))
        c.couple_eyes_closed = any(
            f["eyes_closed"] and f["eyes_reliable"] and roles.get(f["person_id"]) in ("bride", "groom") for f in fs
        )
    important = {p for p, w in weights.items() if w >= 0.5}
    return list(cands.values()), names, important


def generate(db: ProjectDB, cfg_dict: Optional[dict] = None) -> dict:
    cfg = SelectionConfig.from_dict(cfg_dict or db.get_setting("album_config"))
    cands, names, important = gather_candidates(db)
    res = select(cands, cfg, names, important)
    now = time.time()
    with db.tx() as con:
        cur = con.execute(
            "INSERT INTO selection_runs(created_at, config, summary) VALUES (?,?,?)",
            (now, json.dumps(asdict(cfg)), json.dumps(res.summary)),
        )
        run_id = cur.lastrowid
        con.execute("DELETE FROM selection")
        con.executemany(
            "INSERT INTO selection(photo_id, run_id, rank, score, bucket, reasons) VALUES (?,?,?,?,?,?)",
            [(p.id, run_id, rank, p.score, p.bucket, json.dumps({"reasons": p.reasons, "components": p.components}))
             for rank, p in enumerate(res.picks)],
        )
    summary = dict(res.summary)
    summary["run_id"] = run_id
    summary["preference"] = preferences.build(db).describe()
    return summary
