"""Exact-duplicate and near-duplicate (burst / similar-shot) grouping."""
from __future__ import annotations

from typing import Optional

import numpy as np

from .db import ProjectDB, from_blob
from .imaging import hamming

PHASH_MAX_DISTANCE = 8
CLIP_MIN_SIMILARITY = 0.93
TIME_WINDOW_S = 90.0
NEIGHBOURS = 12


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def mark_exact_duplicates(db: ProjectDB) -> int:
    """Photos with identical content hashes: the lowest id is canonical."""
    with db.tx() as con:
        con.execute("UPDATE photos SET duplicate_of=NULL")
        con.execute(
            """
            UPDATE photos SET duplicate_of = (
                SELECT MIN(p2.id) FROM photos p2 WHERE p2.sha256 = photos.sha256 AND p2.status='ok'
            )
            WHERE status='ok' AND sha256 IS NOT NULL AND id != (
                SELECT MIN(p3.id) FROM photos p3 WHERE p3.sha256 = photos.sha256 AND p3.status='ok')
            """
        )
        return con.execute("SELECT COUNT(*) FROM photos WHERE duplicate_of IS NOT NULL").fetchone()[0]


def similar(a: dict, b: dict, ea: Optional[np.ndarray], eb: Optional[np.ndarray]) -> bool:
    if a.get("sha256") and a.get("sha256") == b.get("sha256"):
        return True
    close_in_time = True
    if a.get("taken_ts") and b.get("taken_ts"):
        close_in_time = abs(a["taken_ts"] - b["taken_ts"]) <= TIME_WINDOW_S
    if not close_in_time:
        return False
    if ea is not None and eb is not None:
        if float(ea @ eb) >= CLIP_MIN_SIMILARITY:
            return True
    if a.get("phash") and b.get("phash"):
        return hamming(a["phash"], b["phash"]) <= PHASH_MAX_DISTANCE
    return False


def compute_groups(db: ProjectDB) -> int:
    """Assign group_id to photos that are near-duplicates of a neighbour in capture order."""
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT id, sha256, phash, taken_ts, rel_path FROM photos WHERE status='ok' "
            "ORDER BY COALESCE(taken_ts, 1e18), rel_path"
        )]
        embs = {r["photo_id"]: from_blob(r["vector"]) for r in con.execute("SELECT photo_id, vector FROM embeddings")}
    uf = UnionFind()
    n = len(rows)
    for i in range(n):
        a = rows[i]
        for j in range(i + 1, min(n, i + 1 + NEIGHBOURS)):
            b = rows[j]
            if a.get("taken_ts") and b.get("taken_ts") and b["taken_ts"] - a["taken_ts"] > TIME_WINDOW_S:
                break
            if similar(a, b, embs.get(a["id"]), embs.get(b["id"])):
                uf.union(a["id"], b["id"])
    groups: dict[int, list[int]] = {}
    for r in rows:
        groups.setdefault(uf.find(r["id"]), []).append(r["id"])
    updates = []
    n_groups = 0
    for root, members in groups.items():
        if len(members) > 1:
            n_groups += 1
            updates.extend((root, m) for m in members)
        else:
            updates.append((None, members[0]))
    with db.tx() as con:
        con.executemany("UPDATE photos SET group_id=? WHERE id=?", updates)
    return n_groups
