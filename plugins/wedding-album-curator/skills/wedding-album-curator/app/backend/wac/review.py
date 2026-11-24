"""Review queues and the side-by-side comparison workflow."""
from __future__ import annotations

import json
import time
from typing import Optional

from .db import ProjectDB
from .selection import person_weights

QUEUES = {
    "couple_issues": "Bride or groom: closed eyes, looking away or face cut off",
    "closed_eyes": "Closed eyes (anyone)",
    "blurry": "Blurry photos",
    "exposure": "Too dark or too bright",
    "weak_composition": "Weak composition",
    "duplicates": "Exact duplicate files",
    "uncertain_faces": "Uncertain face matches",
    "uncertain_moments": "Uncertain moment classification",
}


def _photo_faces(con, ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    if not ids:
        return out
    for f in con.execute(
        f"SELECT * FROM faces WHERE photo_id IN ({','.join('?' * len(ids))}) AND assignment!='ignored'", ids
    ):
        out.setdefault(f["photo_id"], []).append(dict(f))
    return out


def queue(db: ProjectDB, kind: str, limit: int = 500) -> list[dict]:
    """Return [{photo_id, reasons:[...]}]. Photos already rejected by the user are skipped."""
    weights, names, roles = person_weights(db)
    base = ("FROM photos p LEFT JOIN quality q ON q.photo_id=p.id LEFT JOIN user_state u ON u.photo_id=p.id "
            "LEFT JOIN events e ON e.photo_id=p.id WHERE p.status='ok' AND COALESCE(u.decision,'')!='rejected' "
            "AND COALESCE(u.reviewed,0)=0 ")
    items: list[dict] = []
    with db.connect() as con:
        if kind == "blurry":
            rows = con.execute(f"SELECT p.id, q.sharpness {base} AND q.sharpness < 0.25 ORDER BY q.sharpness LIMIT ?", (limit,))
            items = [{"photo_id": r["id"], "reasons": [f"Low sharpness ({r['sharpness']:.2f})"]} for r in rows]
        elif kind == "exposure":
            rows = con.execute(f"SELECT p.id, q.brightness, q.exposure {base} AND q.exposure < 0.35 ORDER BY q.exposure LIMIT ?", (limit,))
            items = [{"photo_id": r["id"], "reasons": ["Too dark" if r["brightness"] < 0.4 else "Too bright"]} for r in rows]
        elif kind == "weak_composition":
            rows = con.execute(f"SELECT p.id, q.composition {base} AND q.composition < 0.3 ORDER BY q.composition LIMIT ?", (limit,))
            items = [{"photo_id": r["id"], "reasons": ["Subject poorly placed or cut off by the frame"]} for r in rows]
        elif kind == "duplicates":
            rows = con.execute(f"SELECT p.id, p.duplicate_of {base} AND p.duplicate_of IS NOT NULL LIMIT ?", (limit,))
            items = [{"photo_id": r["id"], "reasons": [f"Identical file to photo #{r['duplicate_of']}"],
                      "related": [r["duplicate_of"]]} for r in rows]
        elif kind == "uncertain_moments":
            rows = con.execute(f"SELECT p.id, e.category, e.confidence {base} AND e.source NOT IN ('user') AND e.confidence < 0.3 "
                               "ORDER BY e.confidence LIMIT ?", (limit,))
            items = [{"photo_id": r["id"], "reasons": [f"Unsure whether this is '{r['category'].replace('_', ' ')}' ({r['confidence']:.0%})"]} for r in rows]
        elif kind == "uncertain_faces":
            rows = con.execute(
                "SELECT f.id, f.photo_id, f.person_id, f.match_conf FROM faces f JOIN photos p ON p.id=f.photo_id "
                "WHERE f.uncertain=1 AND f.assignment='auto' AND p.status='ok' ORDER BY f.match_conf LIMIT ?", (limit,))
            items = [{"photo_id": r["photo_id"], "face_id": r["id"], "person_id": r["person_id"],
                      "reasons": [f"Unsure this is {names.get(r['person_id'], 'person #' + str(r['person_id']))}"
                                  + (f" (similarity {r['match_conf']:.2f})" if r["match_conf"] is not None else "")]}
                     for r in rows]
        elif kind in ("closed_eyes", "couple_issues"):
            ids = [r["id"] for r in con.execute(f"SELECT p.id {base}")]
            faces = _photo_faces(con, ids)
            for pid in ids:
                reasons = []
                for f in faces.get(pid, []):
                    who = names.get(f["person_id"]) or "Someone"
                    is_couple = roles.get(f["person_id"]) in ("bride", "groom")
                    if kind == "couple_issues" and not is_couple:
                        continue
                    if f["eyes_closed"] and f["eyes_reliable"]:
                        reasons.append(f"{who}: eyes appear closed")
                    elif f["eyes_closed"] and kind == "couple_issues":
                        reasons.append(f"{who}: eyes may be closed (low confidence)")
                    if kind == "couple_issues":
                        if (f["frontal"] or 0) < 0.3:
                            reasons.append(f"{who}: looking away from the camera")
                        if f["edge_cut"]:
                            reasons.append(f"{who}: face cut off by the frame")
                        if f["landmarker_found"] == 0 and (f["size_px"] or 0) > 150:
                            reasons.append(f"{who}: face may be partly hidden")
                if reasons:
                    items.append({"photo_id": pid, "reasons": reasons})
                if len(items) >= limit:
                    break
        else:
            raise KeyError(kind)
    return items


def queue_counts(db: ProjectDB) -> dict:
    return {k: len(queue(db, k, limit=5000)) for k in QUEUES}


def mark_reviewed(db: ProjectDB, photo_ids: list[int]) -> None:
    with db.tx() as con:
        for pid in photo_ids:
            db.touch_user_state(con, pid, reviewed=1)


# ---------------- compare ----------------

def _photo_scores(con, ids: list[int], weights: dict, roles: dict) -> dict[int, dict]:
    out = {}
    q = {r["photo_id"]: dict(r) for r in con.execute(
        f"SELECT * FROM quality WHERE photo_id IN ({','.join('?' * len(ids))})", ids)}
    faces = _photo_faces(con, ids)
    for pid in ids:
        qq = q.get(pid, {})
        fs = faces.get(pid, [])
        key = [f for f in fs if weights.get(f["person_id"], 0) >= 0.5] or fs
        eyes_closed = [f for f in fs if f["eyes_closed"] and f["eyes_reliable"]]
        couple_closed = [f for f in eyes_closed if roles.get(f["person_id"]) in ("bride", "groom")]
        face_q = (sum(0.5 * (f["sharpness"] or 0) + 0.5 * (f["frontal"] or 0) for f in key) / len(key)) if key else None
        score = (qq.get("technical") or 0.5) * 0.6 + (face_q if face_q is not None else 0.5) * 0.4
        score -= 0.25 * len(couple_closed) + 0.08 * (len(eyes_closed) - len(couple_closed))
        out[pid] = {
            "score": round(score, 4), "sharpness": qq.get("sharpness"), "exposure": qq.get("exposure"),
            "composition": qq.get("composition"), "face_quality": face_q, "eyes_closed": len(eyes_closed),
            "couple_eyes_closed": len(couple_closed),
            "people": sorted({f["person_id"] for f in fs if f["person_id"] is not None}),
        }
    return out


def _explain(best: dict, other: dict) -> list[str]:
    r = []
    if best["couple_eyes_closed"] < other["couple_eyes_closed"]:
        r.append("The couple's eyes are open")
    elif best["eyes_closed"] < other["eyes_closed"]:
        r.append("Fewer closed eyes")
    for k, label in (("sharpness", "Sharper"), ("exposure", "Better exposed"), ("composition", "Better composed"),
                     ("face_quality", "Clearer faces")):
        a, b = best.get(k), other.get(k)
        if a is not None and b is not None and a - b >= 0.08:
            r.append(f"{label} ({a:.2f} vs {b:.2f})")
    return r or ["Very similar; slightly higher overall quality"]


def compare_group(db: ProjectDB, group_id: int) -> Optional[dict]:
    weights, names, roles = person_weights(db)
    with db.connect() as con:
        ids = [r["id"] for r in con.execute(
            "SELECT p.id FROM photos p LEFT JOIN user_state u ON u.photo_id=p.id "
            "WHERE p.group_id=? AND p.status='ok' ORDER BY COALESCE(p.taken_ts,0), p.rel_path", (group_id,))]
        if len(ids) < 2:
            return None
        sc = _photo_scores(con, ids, weights, roles)
        states = {r["photo_id"]: dict(r) for r in con.execute(
            f"SELECT * FROM user_state WHERE photo_id IN ({','.join('?' * len(ids))})", ids)}
    pref = {}
    try:
        from .preferences import build

        pm = build(db)
        pref = pm.scores if pm.method != "none" else {}
    except Exception:
        pass
    for pid in ids:
        if pid in pref:
            sc[pid]["score"] = round(sc[pid]["score"] + 0.1 * (pref[pid] - 0.5), 4)
    ranked = sorted(ids, key=lambda i: -sc[i]["score"])
    best = ranked[0]
    second = ranked[1]
    has_couple = any(roles.get(p) in ("bride", "groom") for i in ids for p in sc[i]["people"])
    return {
        "group_id": group_id,
        "photos": [{"id": i, **sc[i], "decision": states.get(i, {}).get("decision")} for i in ids],
        "recommended": best,
        "explanation": _explain(sc[best], sc[second]),
        "involves_couple": has_couple,
        "people_names": {p: names.get(p) for i in ids for p in sc[i]["people"] if names.get(p)},
    }


def next_group(db: ProjectDB, mode: str = "all", after: int = 0) -> Optional[dict]:
    """Next unresolved similar-photo group (a group is resolved when the user decided on all but one)."""
    _, _, roles = person_weights(db)
    couple_ids = [p for p, r in roles.items() if r in ("bride", "groom")]
    with db.connect() as con:
        sql = (
            "SELECT p.group_id, COUNT(*) n, SUM(CASE WHEN u.decision IS NULL THEN 1 ELSE 0 END) undecided "
            "FROM photos p LEFT JOIN user_state u ON u.photo_id=p.id WHERE p.group_id IS NOT NULL AND p.status='ok' "
        )
        params: list = []
        if mode == "couple":
            if not couple_ids:
                return None
            sql += (f"AND p.group_id IN (SELECT p2.group_id FROM photos p2 JOIN faces f ON f.photo_id=p2.id "
                    f"WHERE f.person_id IN ({','.join('?' * len(couple_ids))})) ")
            params += couple_ids
        sql += "GROUP BY p.group_id HAVING n >= 2 AND undecided >= 2 AND p.group_id > ? ORDER BY p.group_id LIMIT 1"
        params.append(after)
        row = con.execute(sql, params).fetchone()
        remaining = con.execute(
            "SELECT COUNT(*) FROM (SELECT p.group_id FROM photos p LEFT JOIN user_state u ON u.photo_id=p.id "
            "WHERE p.group_id IS NOT NULL AND p.status='ok' GROUP BY p.group_id "
            "HAVING COUNT(*) >= 2 AND SUM(CASE WHEN u.decision IS NULL THEN 1 ELSE 0 END) >= 2)"
        ).fetchone()[0]
    if not row:
        return None
    g = compare_group(db, row["group_id"])
    if g:
        g["remaining_groups"] = remaining
    return g


def decide(db: ProjectDB, winner_id: int, loser_ids: list[int], reject_losers: bool) -> None:
    now = time.time()
    with db.tx() as con:
        db.touch_user_state(con, winner_id, decision="selected")
        for lid in loser_ids:
            con.execute("INSERT INTO compare_decisions(winner_id, loser_id, created_at) VALUES (?,?,?)", (winner_id, lid, now))
            if reject_losers:
                db.touch_user_state(con, lid, decision="rejected")
