"""Lightweight, transparent preference learning from explicit feedback.

Signals (only those recorded after the last reset are used):
  positive: favorites, ratings >= 4, photos the user selected, comparison winners
  negative: ratings <= 2, photos the user rejected, comparison losers

Method:
  - >= 6 positives and >= 6 negatives: L2-regularized logistic regression on CLIP
    image embeddings (a small linear model fitted locally in well under a second).
  - otherwise, >= 3 positives: cosine similarity to the mean positive embedding.
  - otherwise: no preference signal (score 0.5 for everyone).

This adapts ranking to the couple's choices; it is not a trained neural network.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .db import ProjectDB, from_blob


@dataclass
class PreferenceModel:
    method: str = "none"
    positives: int = 0
    negatives: int = 0
    scores: dict[int, float] = field(default_factory=dict)
    note: str = ""

    def describe(self) -> dict:
        return {"method": self.method, "positives": self.positives, "negatives": self.negatives, "note": self.note}


def feedback(db: ProjectDB) -> tuple[set[int], set[int]]:
    since = db.get_setting("preferences_reset_at", 0.0)
    pos: set[int] = set()
    neg: set[int] = set()
    with db.connect() as con:
        for r in con.execute("SELECT * FROM user_state WHERE updated_at >= ?", (since,)):
            if r["favorite"] or (r["rating"] or 0) >= 4 or r["decision"] == "selected":
                pos.add(r["photo_id"])
            if (r["rating"] is not None and r["rating"] <= 2) or r["decision"] == "rejected":
                neg.add(r["photo_id"])
        for r in con.execute("SELECT winner_id, loser_id FROM compare_decisions WHERE created_at >= ?", (since,)):
            pos.add(r["winner_id"])
            neg.add(r["loser_id"])
    both = pos & neg
    return pos - both, neg - both


def build(db: ProjectDB) -> PreferenceModel:
    pos, neg = feedback(db)
    with db.connect() as con:
        embs = {r["photo_id"]: from_blob(r["vector"]) for r in con.execute("SELECT photo_id, vector FROM embeddings")}
    model = PreferenceModel(positives=len(pos), negatives=len(neg))
    if not embs:
        model.method = "none"
        model.note = "Preference learning needs the local visual model (CLIP). Your choices are saved and will be used once it is installed."
        return model
    pos = {p for p in pos if p in embs}
    neg = {n for n in neg if n in embs}
    ids = list(embs)
    X = np.stack([embs[i] for i in ids])
    if len(pos) >= 6 and len(neg) >= 6:
        from sklearn.linear_model import LogisticRegression

        Xt = np.stack([embs[i] for i in list(pos) + list(neg)])
        y = np.array([1] * len(pos) + [0] * len(neg))
        clf = LogisticRegression(C=0.5, max_iter=500, class_weight="balanced")
        clf.fit(Xt, y)
        p = clf.predict_proba(X)[:, 1]
        model.method = "logistic_regression"
    elif len(pos) >= 3:
        c = np.mean([embs[i] for i in pos], axis=0)
        c /= np.linalg.norm(c)
        sims = X @ c
        lo, hi = np.percentile(sims, 5), np.percentile(sims, 99)
        p = np.clip((sims - lo) / max(hi - lo, 1e-6), 0, 1)
        model.method = "similarity_to_favorites"
    else:
        return model
    model.scores = {pid: float(v) for pid, v in zip(ids, p)}
    return model


def reset(db: ProjectDB) -> None:
    """Forget learned preferences: feedback recorded before now is no longer used for learning.
    The user's explicit decisions (favorites, selections, rejections) are kept."""
    db.set_setting("preferences_reset_at", time.time())
    with db.tx() as con:
        con.execute("DELETE FROM compare_decisions")
