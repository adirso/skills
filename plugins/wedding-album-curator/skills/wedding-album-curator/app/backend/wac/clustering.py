"""Probabilistic grouping of face descriptors into people, respecting user corrections.

Algorithm (conservative by design):
1. Build a k-nearest-neighbour graph (k=30) over SFace descriptors, keeping only edges with
   cosine similarity >= EDGE_THRESHOLD (stricter than OpenCV's 0.363 verification point).
2. Run Chinese Whispers graph clustering (Biemann 2006), as used by dlib for faces, then
   merge clusters whose centroids clearly match (cosine >= 0.55; bursts of identical shots
   otherwise hide cross-photo links to the same person).
   Cannot-link constraint: a person appears at most once per photo. Faces in the same
   photo are never linked, clusters that share photos are never merged, and a cluster
   with several faces in the same photos (different people chained together, e.g. the
   bride and bridesmaids) is re-split with a stricter threshold.
3. Map each cluster to an existing person when most of its faces already belonged to
   that person (keeps names/merges stable across runs). User-confirmed faces count triple.
4. User-assigned faces are never moved; a face is never auto-assigned to a person the
   user removed it from.
5. Leftover faces join the nearest person only with a clear margin; low-similarity
   matches are flagged as uncertain for review.
"""
from __future__ import annotations

import json
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from .db import ProjectDB, from_blob

EDGE_THRESHOLD = 0.45
ASSIGN_THRESHOLD = 0.50
ASSIGN_MARGIN = 0.05
UNCERTAIN_BELOW = 0.45
MIN_CLUSTER_SIZE = 3
MIN_DET_SCORE = 0.85
KNN = 30
CENTROID_MERGE = 0.55  # second pass: merge clusters whose mean descriptors clearly match
CONFLICT_RATE = 0.02  # a person may have >1 face in at most ~2% of their photos (mirrors, prints)
SPLIT_STEP = 0.05
SPLIT_MAX = 0.75


def knn_graph(emb: np.ndarray, k: int = KNN, threshold: float = EDGE_THRESHOLD, chunk: int = 2048,
              photo_ids: np.ndarray | None = None) -> list[dict[int, float]]:
    n = len(emb)
    adj: list[dict[int, float]] = [dict() for _ in range(n)]
    if n < 2:
        return adj
    kk = min(k + 1, n)
    for start in range(0, n, chunk):
        sims = emb[start:start + chunk] @ emb.T
        if photo_ids is not None:  # cannot-link: two faces in one photo are different people
            sims[photo_ids[start:start + chunk, None] == photo_ids[None, :]] = -1.0
        idx = np.argpartition(-sims, kk - 1, axis=1)[:, :kk]
        for r, row in enumerate(idx):
            i = start + r
            for j in row:
                j = int(j)
                s = float(sims[r, j])
                if j != i and s >= threshold:
                    adj[i][j] = s
                    adj[j][i] = s
    return adj


def chinese_whispers(adj: list[dict[int, float]], iterations: int = 20, seed: int = 0) -> np.ndarray:
    n = len(adj)
    labels = list(range(n))
    rng = random.Random(seed)
    order = list(range(n))
    for _ in range(iterations):
        rng.shuffle(order)
        changed = 0
        for i in order:
            nb = adj[i]
            if not nb:
                continue
            weights: dict[int, float] = defaultdict(float)
            for j, w in nb.items():
                weights[labels[j]] += w
            best = max(weights.items(), key=lambda kv: (kv[1], -kv[0]))[0]
            if best != labels[i]:
                labels[i] = best
                changed += 1
        if changed == 0:
            break
    return np.array(labels)


def _conflicts(photo_ids: np.ndarray, members: np.ndarray) -> int:
    """Photos in which this cluster has more than one face (a person appears once per photo)."""
    _, counts = np.unique(photo_ids[members], return_counts=True)
    return int((counts > 1).sum())


def merge_close_clusters(emb: np.ndarray, labels: np.ndarray, threshold: float = CENTROID_MERGE,
                         photo_ids: np.ndarray | None = None) -> np.ndarray:
    """Merge clusters whose centroids are very similar.

    Needed because bursts of near-identical shots fill a face's k-NN list with copies of
    itself, hiding the (weaker but genuine) links to the same person in other photos.
    Two clusters that appear together in the same photos are never merged."""
    uniq = np.unique(labels)
    if len(uniq) < 2:
        return labels
    cents = np.stack([emb[labels == u].mean(axis=0) for u in uniq])
    cents /= np.linalg.norm(cents, axis=1, keepdims=True) + 1e-9
    parent = list(range(len(uniq)))
    photos = [set(photo_ids[labels == u].tolist()) for u in uniq] if photo_ids is not None else None

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    sims = cents @ cents.T
    ii, jj = np.where(np.triu(sims, 1) >= threshold)
    order = np.argsort(-sims[ii, jj])  # most similar pairs first
    for a, b in zip(ii[order], jj[order]):
        ra, rb = find(int(a)), find(int(b))
        if ra == rb:
            continue
        if photos is not None:
            overlap = len(photos[ra] & photos[rb])
            if overlap > max(1, CONFLICT_RATE * min(len(photos[ra]), len(photos[rb]))):
                continue
        lo, hi = min(ra, rb), max(ra, rb)
        parent[hi] = lo
        if photos is not None:
            photos[lo] |= photos[hi]
    mapping = {int(u): int(uniq[find(k)]) for k, u in enumerate(uniq)}
    return np.array([mapping[int(l)] for l in labels])


def split_conflicting(emb: np.ndarray, labels: np.ndarray, photo_ids: np.ndarray,
                      threshold: float = EDGE_THRESHOLD) -> np.ndarray:
    """Re-cluster, with stricter similarity, any cluster that contains several faces from the
    same photos — the signature of different people chained together."""
    labels = labels.copy()
    next_label = int(labels.max()) + 1 if len(labels) else 0
    queue = [(int(u), threshold) for u in np.unique(labels)]
    while queue:
        lab, thr = queue.pop()
        members = np.where(labels == lab)[0]
        if len(members) < 2:
            continue
        n_photos = len(np.unique(photo_ids[members]))
        if _conflicts(photo_ids, members) <= max(1, CONFLICT_RATE * n_photos):
            continue
        new_thr = thr + SPLIT_STEP
        if new_thr > SPLIT_MAX:
            continue
        sub = chinese_whispers(knn_graph(emb[members], threshold=new_thr, photo_ids=photo_ids[members]))
        parts = np.unique(sub)
        if len(parts) == 1:
            queue.append((lab, new_thr))
            continue
        for k, part in enumerate(parts):
            idx = members[sub == part]
            if k == 0:
                queue.append((lab, new_thr))
            else:
                labels[idx] = next_label
                queue.append((next_label, new_thr))
                next_label += 1
    return labels


def cluster_embeddings(emb: np.ndarray, threshold: float = EDGE_THRESHOLD,
                       photo_ids: np.ndarray | None = None) -> np.ndarray:
    labels = chinese_whispers(knn_graph(emb, threshold=threshold, photo_ids=photo_ids))
    if photo_ids is not None:
        labels = split_conflicting(emb, labels, photo_ids, threshold)
    return merge_close_clusters(emb, labels, photo_ids=photo_ids)


@dataclass
class ClusterStats:
    faces: int = 0
    clustered: int = 0
    persons: int = 0
    new_persons: int = 0
    uncertain: int = 0


def recluster(db: ProjectDB, min_cluster_size: int = MIN_CLUSTER_SIZE) -> ClusterStats:
    stats = ClusterStats()
    with db.connect() as con:
        rows = con.execute(
            "SELECT f.id, f.photo_id, f.embedding, f.det_score, f.person_id, f.assignment, f.excluded_person_ids, "
            "f.frontal, f.size_px, f.sharpness FROM faces f JOIN photos p ON p.id=f.photo_id "
            "WHERE f.embedding IS NOT NULL AND p.status='ok'"
        ).fetchall()
        persons = {r["id"]: dict(r) for r in con.execute("SELECT * FROM persons")}
    if not rows:
        return stats
    ids = np.array([r["id"] for r in rows])
    emb = np.stack([from_blob(r["embedding"]) for r in rows])
    photo_of = np.array([r["photo_id"] for r in rows])
    prev_person = {r["id"]: r["person_id"] for r in rows}
    assignment = {r["id"]: r["assignment"] for r in rows}
    excluded = {r["id"]: set(json.loads(r["excluded_person_ids"] or "[]")) for r in rows}
    stats.faces = len(rows)

    eligible = np.array([
        (r["assignment"] == "user") or (r["assignment"] == "auto" and (r["det_score"] or 0) >= MIN_DET_SCORE)
        for r in rows
    ])
    el_idx = np.where(eligible)[0]
    labels = np.full(len(rows), -1)
    if len(el_idx):
        labels[el_idx] = cluster_embeddings(emb[el_idx], photo_ids=photo_of[el_idx])

    new_person: dict[int, int | None] = {}
    now = time.time()
    created: list[int] = []
    with db.tx() as con:
        # --- map clusters to persons
        cluster_members: dict[int, list[int]] = defaultdict(list)
        for i, lab in enumerate(labels):
            if lab >= 0:
                cluster_members[int(lab)].append(i)
        claimed: set[int] = set()
        # biggest clusters first; an existing person is claimed by one cluster only, so a
        # previously mixed group that is now split does not silently re-merge
        for lab, members in sorted(cluster_members.items(), key=lambda kv: -len(kv[1])):
            votes: Counter = Counter()
            for i in members:
                pid = prev_person[ids[i]]
                if pid is not None and pid in persons and pid not in claimed:
                    votes[pid] += 3 if assignment[ids[i]] == "user" else 1
            total = sum(3 if assignment[ids[i]] == "user" else 1 for i in members)
            target = None
            if votes:
                pid, v = votes.most_common(1)[0]
                if v * 2 >= total:
                    target = pid
            if target is not None:
                claimed.add(target)
            if target is None and len(members) >= min_cluster_size:
                cur = con.execute(
                    "INSERT INTO persons(importance, created_at) VALUES ('other', ?)", (now,)
                )
                target = cur.lastrowid
                persons[target] = {"id": target, "user_touched": 0}
                created.append(target)
            for i in members:
                fid = int(ids[i])
                if assignment[fid] == "user":
                    continue
                new_person[fid] = target if target is not None and target not in excluded[fid] else None
            if len(members) >= min_cluster_size:
                stats.clustered += len(members)

        # --- centroids of the resulting persons
        final = {}
        for i, fid in enumerate(ids):
            fid = int(fid)
            if assignment[fid] == "user":
                final[fid] = prev_person[fid]
            elif assignment[fid] == "ignored":
                final[fid] = None
            else:
                final[fid] = new_person.get(fid)
        by_person: dict[int, list[int]] = defaultdict(list)
        for i, fid in enumerate(ids):
            pid = final[int(fid)]
            if pid is not None:
                by_person[pid].append(i)
        pids = list(by_person)
        if pids:
            cents = np.stack([emb[by_person[p]].mean(axis=0) for p in pids])
            cents /= np.linalg.norm(cents, axis=1, keepdims=True) + 1e-9
        else:
            cents = np.zeros((0, emb.shape[1]), dtype=np.float32)

        # --- leftovers: nearest person with a clear margin; compute confidence for all
        updates = []
        for i, fid in enumerate(ids):
            fid = int(fid)
            pid = final[fid]
            conf = None
            if len(pids):
                sims = cents @ emb[i]
                order = np.argsort(-sims)
                if pid is None and assignment[fid] == "auto":
                    for rank, j in enumerate(order[:3]):
                        cand = pids[j]
                        if cand in excluded[fid]:
                            continue
                        second = sims[order[rank + 1]] if rank + 1 < len(order) else -1
                        if sims[j] >= ASSIGN_THRESHOLD and sims[j] - second >= ASSIGN_MARGIN:
                            pid = cand
                        break
                if pid is not None and pid in pids:
                    conf = float(sims[pids.index(pid)])
            uncertain = int(assignment[fid] == "auto" and pid is not None and conf is not None and conf < UNCERTAIN_BELOW)
            stats.uncertain += uncertain
            updates.append((pid, conf, uncertain, fid))
        con.executemany(
            "UPDATE faces SET person_id=?, match_conf=?, uncertain=CASE WHEN assignment='user' THEN 0 ELSE ? END WHERE id=?",
            updates,
        )
        # --- drop empty, untouched persons; refresh representative faces
        con.execute(
            "DELETE FROM persons WHERE user_touched=0 AND role IS NULL AND name IS NULL "
            "AND id NOT IN (SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)"
        )
        refresh_representatives(con)
        stats.persons = con.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        stats.new_persons = sum(
            1 for p in created if con.execute("SELECT 1 FROM persons WHERE id=?", (p,)).fetchone()
        )
    return stats


def refresh_representatives(con) -> None:
    con.execute(
        """
        UPDATE persons SET rep_face_id = (
            SELECT f.id FROM faces f WHERE f.person_id = persons.id
            ORDER BY (f.assignment='user') DESC,
                     (COALESCE(f.det_score,0) * COALESCE(f.frontal,0) * COALESCE(f.sharpness,0.5)
                      * MIN(COALESCE(f.size_px,0), 400)) DESC
            LIMIT 1)
        """
    )


# ---------------- user corrections ----------------

def merge_persons(db: ProjectDB, target_id: int, source_ids: list[int]) -> None:
    with db.tx() as con:
        tgt = con.execute("SELECT * FROM persons WHERE id=?", (target_id,)).fetchone()
        if not tgt:
            raise KeyError(target_id)
        for sid in source_ids:
            if sid == target_id:
                continue
            src = con.execute("SELECT * FROM persons WHERE id=?", (sid,)).fetchone()
            if not src:
                continue
            # keep the more specific metadata
            if not tgt["name"] and src["name"]:
                con.execute("UPDATE persons SET name=? WHERE id=?", (src["name"], target_id))
            if not tgt["role"] and src["role"]:
                con.execute("UPDATE persons SET role=? WHERE id=?", (src["role"], target_id))
            con.execute("UPDATE faces SET person_id=? WHERE person_id=?", (target_id, sid))
            # Merges are explicit identity confirmations
            con.execute("UPDATE faces SET assignment='user', uncertain=0 WHERE person_id=? AND assignment='auto'", (target_id,))
            con.execute("DELETE FROM persons WHERE id=?", (sid,))
        con.execute("UPDATE persons SET user_touched=1 WHERE id=?", (target_id,))
        refresh_representatives(con)


def move_faces(db: ProjectDB, face_ids: list[int], target_person_id: int | None, new_person: bool = False) -> int | None:
    """Move faces to another person (or to a new person = split). Returns the target id."""
    with db.tx() as con:
        if new_person:
            cur = con.execute("INSERT INTO persons(importance, user_touched, created_at) VALUES ('other', 1, ?)", (time.time(),))
            target_person_id = cur.lastrowid
        for fid in face_ids:
            row = con.execute("SELECT person_id, excluded_person_ids FROM faces WHERE id=?", (fid,)).fetchone()
            if not row:
                continue
            excl = set(json.loads(row["excluded_person_ids"] or "[]"))
            if row["person_id"] is not None and row["person_id"] != target_person_id:
                excl.add(row["person_id"])
            excl.discard(target_person_id)
            con.execute(
                "UPDATE faces SET person_id=?, assignment=?, uncertain=0, excluded_person_ids=? WHERE id=?",
                (target_person_id, "user" if target_person_id is not None else "auto", json.dumps(sorted(excl)), fid),
            )
        refresh_representatives(con)
    return target_person_id


def confirm_faces(db: ProjectDB, face_ids: list[int]) -> None:
    with db.tx() as con:
        con.executemany(
            "UPDATE faces SET assignment='user', uncertain=0 WHERE id=? AND person_id IS NOT NULL",
            [(f,) for f in face_ids],
        )


def mark_uncertain(db: ProjectDB, face_ids: list[int], uncertain: bool = True) -> None:
    with db.tx() as con:
        con.executemany("UPDATE faces SET uncertain=? WHERE id=?", [(int(uncertain), f) for f in face_ids])


def ignore_faces(db: ProjectDB, face_ids: list[int]) -> None:
    """Not a real face / a stranger in the background: exclude from people entirely."""
    with db.tx() as con:
        con.executemany(
            "UPDATE faces SET assignment='ignored', person_id=NULL, uncertain=0 WHERE id=?",
            [(f,) for f in face_ids],
        )
