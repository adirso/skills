"""Optional semantic analysis with the user's chosen VisionProvider.

Safety rules enforced here (not just in the UI):
- No provider is ever chosen implicitly; the job uses exactly the configured provider.
- Cloud providers require recorded consent; otherwise nothing is uploaded.
- Results are cached; cached photos are never re-sent.
- The Anthropic API spending limit is checked before every request.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PIL import Image

from .db import ProjectDB
from .imaging import jpeg_bytes
from .jobs import JobContext
from .providers import get_provider
from .providers.base import (BudgetExceeded, ConsentRequired, ImageInput, ProviderError, cache_get, cache_put,
                             require_consent, spent_usd)


def provider_settings(db: ProjectDB) -> dict:
    return db.get_setting("ai_provider", {"id": "none", "model": "", "options": {}})


def make_budget_check(db: ProjectDB, provider_id: str):
    def check(worst_case: float) -> None:
        limit = db.get_setting("spending_limit_usd")
        if limit is None:
            return
        spent = spent_usd(db, provider_id)
        if spent + worst_case > float(limit):
            raise BudgetExceeded(
                f"Spending limit reached: ${spent:.2f} spent of ${float(limit):.2f}. "
                "Raise the limit to continue. (This limit is enforced by this app, not by Anthropic.)"
            )
    return check


def select_photo_ids(db: ProjectDB, scope: str) -> list[int]:
    with db.connect() as con:
        if scope == "album":
            q = "SELECT photo_id FROM selection UNION SELECT photo_id FROM user_state WHERE decision='selected'"
        elif scope == "uncategorized":
            q = ("SELECT p.id FROM photos p LEFT JOIN events e ON e.photo_id=p.id "
                 "WHERE p.status='ok' AND p.duplicate_of IS NULL AND (e.photo_id IS NULL OR e.confidence < 0.35)")
        else:
            q = "SELECT id FROM photos WHERE status='ok' AND duplicate_of IS NULL"
        return [r[0] for r in con.execute(q)]


def build_provider(db: ProjectDB):
    s = provider_settings(db)
    prov = get_provider(s.get("id", "none"), s.get("model", ""), s.get("options", {}),
                        budget_check=make_budget_check(db, s.get("id", "")))
    return prov


def estimate(db: ProjectDB, scope: str) -> dict:
    prov = build_provider(db)
    ids = select_photo_ids(db, scope)
    if prov is None:
        return {"provider": "none", "images": len(ids)}
    with db.connect() as con:
        hashes = {r["id"]: r["sha256"] for r in con.execute(
            f"SELECT id, sha256 FROM photos WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else {}
    uncached = [i for i in ids if not (hashes.get(i) and cache_get(db, prov, hashes[i]))]
    est = prov.estimate(len(uncached))
    est.update(provider=prov.id, model=prov.model, total=len(ids), cached=len(ids) - len(uncached),
               spent_usd=round(spent_usd(db, prov.id), 4), spending_limit_usd=db.get_setting("spending_limit_usd"))
    return est


def run_ai(project, ctx: JobContext) -> dict:
    db: ProjectDB = project.db
    prov = build_provider(db)
    if prov is None:
        return {"skipped": "No AI provider configured"}
    require_consent(db, prov)  # raises ConsentRequired before anything is uploaded
    caps = prov.capabilities()
    if not caps.available:
        raise ProviderError(caps.status)
    scope = ctx.params.get("scope", "album")
    ids = select_photo_ids(db, scope)
    with db.connect() as con:
        rows = {r["id"]: dict(r) for r in con.execute(
            f"SELECT id, sha256 FROM photos WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else {}
    size = int(prov.options.get("image_size", 1024))
    stats = {"analyzed": 0, "cached": 0, "failed": 0, "stopped_reason": None}
    ctx.progress(stage="ai", done=0, total=len(ids), message=f"Analyzing with {caps.name}…", force=True)

    def one(pid: int) -> Optional[str]:
        r = rows.get(pid)
        if not r or not r["sha256"]:
            return "skip"
        cached = cache_get(db, prov, r["sha256"])
        if cached:
            apply_result(db, pid, cached)
            return "cached"
        with Image.open(project.preview_path(pid)) as im:
            im = im.convert("RGB")
            data = jpeg_bytes(im, size, quality=85)
            im.thumbnail((size, size))
            w, h = im.size
        res = prov.analyze_image(ImageInput(pid, r["sha256"], data, w, h))
        cache_put(db, prov, r["sha256"], res, pid)
        apply_result(db, pid, json.loads(res.result_json()))
        return "analyzed"

    done = 0
    workers = max(1, caps.max_concurrency)
    if db.get_setting("spending_limit_usd") is not None:
        # One request at a time so the pre-request worst-case check is a strict guarantee.
        workers = 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(ids), workers * 2):
            ctx.check()
            futs = [pool.submit(one, pid) for pid in ids[start:start + workers * 2]]
            for f in futs:
                try:
                    out = f.result()
                    if out == "analyzed":
                        stats["analyzed"] += 1
                    elif out == "cached":
                        stats["cached"] += 1
                except (BudgetExceeded, ConsentRequired) as e:
                    stats["stopped_reason"] = str(e)
                except ProviderError as e:
                    stats["failed"] += 1
                    stats["last_error"] = str(e)
                done += 1
            ctx.progress(done=done, message=f"{done}/{len(ids)} · spent ${spent_usd(db, prov.id):.2f}")
            if stats["stopped_reason"]:
                break
            if stats["failed"] >= 10 and stats["analyzed"] == 0:
                stats["stopped_reason"] = "Stopped after repeated failures: " + stats.get("last_error", "")
                break
    db.set_setting("active_ai_result_source", f"{prov.id}:{prov.model}")
    stats["spent_usd_total"] = round(spent_usd(db, prov.id), 4)
    return stats


def apply_result(db: ProjectDB, photo_id: int, result: dict) -> None:
    """Use a confident AI moment label unless the user set the category themselves."""
    if result.get("category_confidence", 0) < 0.5:
        return
    with db.tx() as con:
        con.execute(
            "INSERT INTO events(photo_id, category, confidence, source, scores) VALUES (?,?,?,'vlm',?) "
            "ON CONFLICT(photo_id) DO UPDATE SET category=excluded.category, confidence=excluded.confidence, "
            "source='vlm', scores=excluded.scores WHERE events.source != 'user'",
            (photo_id, result["category"], result["category_confidence"], json.dumps({"caption": result.get("caption")})),
        )
