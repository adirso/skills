"""HTTP API (FastAPI). Binds to localhost only; serves the built frontend.

Security model for a local app:
- The server binds to 127.0.0.1 by default.
- Host header must be localhost/127.0.0.1 (defeats DNS-rebinding attacks).
- Requests carrying an Origin header must come from this app's own origin.
- All /api calls require a per-launch session cookie (SameSite=Strict, HttpOnly),
  which other websites cannot cause the browser to send.
- Photos are only served by database id, never by client-supplied filesystem paths.
"""
from __future__ import annotations

import json
import secrets as pysecrets
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from . import (ai_analysis, clustering, config, embeddings, events, export, hardware, models_registry as mr,
               preferences, review, secrets, selection)
from .imaging import HEIF_SUPPORTED
from .jobs import JobContext
from .pipeline import Project, run_analysis
from .projects import pick_folder, registry
from .providers import PROVIDER_IDS, get_provider
from .providers import ollama as ollama_mod
from .providers.base import CLOUD_WARNING, ConsentRequired, ProviderError, has_consent, record_consent, spent_usd
from .providers import pricing
from .scanner import PathError, safe_join, validate_source_dir

SESSION_TOKEN = pysecrets.token_urlsafe(32)
COOKIE = "wac_session"

app = FastAPI(title="Wedding Album Curator", version=config.VERSION, docs_url=None, redoc_url=None)


def allowed_hosts() -> set[str]:
    port = app.state.port if hasattr(app.state, "port") else config.DEFAULT_PORT
    return {f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost", "testserver",
            "127.0.0.1:5173", "localhost:5173"}


@app.middleware("http")
async def security(request: Request, call_next):
    host = request.headers.get("host", "")
    if host not in allowed_hosts():
        return JSONResponse({"detail": "Forbidden host"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin.replace("http://", "") not in allowed_hosts():
        return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
    path = request.url.path
    if path.startswith("/api/") and path != "/api/session":
        if request.cookies.get(COOKIE) != SESSION_TOKEN:
            return JSONResponse({"detail": "Missing session. Reload the app."}, status_code=401)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def set_session(resp: Response) -> None:
    resp.set_cookie(COOKIE, SESSION_TOKEN, httponly=True, samesite="strict", path="/")


@app.exception_handler(PathError)
async def path_error(_: Request, exc: PathError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(ConsentRequired)
async def consent_error(_: Request, exc: ConsentRequired):
    return JSONResponse({"detail": str(exc), "consent_required": True}, status_code=409)


@app.exception_handler(ProviderError)
async def provider_error(_: Request, exc: ProviderError):
    return JSONResponse({"detail": str(exc)}, status_code=502)


# ---------------- global ----------------

@app.get("/api/session")
def session() -> Response:
    resp = JSONResponse({"ok": True})
    set_session(resp)
    return resp


@app.get("/api/status")
def status() -> dict:
    return {
        "version": config.VERSION,
        "data_dir": str(config.data_dir()),
        "heif_supported": HEIF_SUPPORTED,
        "clip_available": embeddings.available(),
        "face_models": mr.is_installed("yunet") and mr.is_installed("sface"),
        "eye_model": mr.is_installed("face_landmarker"),
        "telemetry": False,
    }


_hw_cache: dict = {}


@app.get("/api/hardware")
def get_hardware() -> dict:
    if "info" not in _hw_cache:
        _hw_cache["info"] = hardware.detect()
    info = _hw_cache["info"]
    return {"info": info, "recommendation": hardware.recommend(info)}


@app.get("/api/models")
def list_models() -> list[dict]:
    return mr.downloads.status()


class ModelDownload(BaseModel):
    ids: list[str]
    approved: bool = False


@app.post("/api/models/download")
def download_models(body: ModelDownload) -> dict:
    if not body.approved:
        raise HTTPException(400, "Model downloads require explicit approval.")
    try:
        mr.downloads.start(body.ids)
    except KeyError as e:
        raise HTTPException(404, f"Unknown model {e}")
    return {"started": body.ids}


@app.delete("/api/models/{model_id}")
def delete_model(model_id: str) -> dict:
    if model_id not in mr.MODELS:
        raise HTTPException(404)
    mr.downloads.delete(model_id)
    if model_id == "clip_vit_b32":
        embeddings.unload()
    return {"deleted": model_id}


@app.post("/api/pick-folder")
def api_pick_folder() -> dict:
    return {"path": pick_folder()}


class FolderBody(BaseModel):
    path: str


@app.post("/api/validate-folder")
def validate_folder(body: FolderBody) -> dict:
    from .scanner import iter_image_files

    p = validate_source_dir(body.path)
    n = 0
    for _ in iter_image_files(p):
        n += 1
        if n >= 20000:
            break
    return {"path": str(p), "photo_count": n, "capped": n >= 20000}


# ---------------- projects ----------------

class ProjectCreate(BaseModel):
    name: str = ""
    source_dir: str


@app.get("/api/projects")
def projects() -> list[dict]:
    return registry.list()


@app.post("/api/projects")
def create_project(body: ProjectCreate) -> dict:
    return registry.create(body.name, body.source_dir)


def proj(pid: str) -> tuple[Project, Any]:
    try:
        return registry.get(pid)
    except KeyError:
        raise HTTPException(404, "Project not found")


@app.patch("/api/projects/{pid}")
def rename_project(pid: str, body: dict = Body(...)) -> dict:
    proj(pid)
    registry.rename(pid, str(body.get("name", "")))
    return {"ok": True}


@app.delete("/api/projects/{pid}")
def delete_project(pid: str) -> dict:
    registry.delete(pid)
    return {"deleted": pid, "originals_untouched": True}


@app.get("/api/projects/{pid}/dashboard")
def dashboard(pid: str) -> dict:
    p, jm = proj(pid)
    with p.db.connect() as con:
        one = lambda q, *a: con.execute(q, a).fetchone()[0]
        d = {
            "name": p.name,
            "source_dir": str(p.source_dir),
            "source_available": p.source_dir.is_dir(),
            "total": one("SELECT COUNT(*) FROM photos WHERE status!='missing'"),
            "processed": one("SELECT COUNT(*) FROM photos WHERE status='ok' AND stage_quality=1"),
            "errors": one("SELECT COUNT(*) FROM photos WHERE status='error'"),
            "missing": one("SELECT COUNT(*) FROM photos WHERE status='missing'"),
            "faces": one("SELECT COUNT(*) FROM faces"),
            "people": one("SELECT COUNT(*) FROM persons WHERE hidden=0"),
            "named_people": one("SELECT COUNT(*) FROM persons WHERE name IS NOT NULL OR role IS NOT NULL"),
            "couple_identified": one("SELECT COUNT(DISTINCT role) FROM persons WHERE role IN ('bride','groom')"),
            "suggested": one("SELECT COUNT(*) FROM selection"),
            "selected": one("SELECT COUNT(*) FROM user_state WHERE decision='selected'"),
            "rejected": one("SELECT COUNT(*) FROM user_state WHERE decision='rejected'"),
            "favorites": one("SELECT COUNT(*) FROM user_state WHERE favorite=1"),
            "similar_groups": one("SELECT COUNT(DISTINCT group_id) FROM photos WHERE group_id IS NOT NULL"),
            "duplicates": one("SELECT COUNT(*) FROM photos WHERE duplicate_of IS NOT NULL"),
            "faces_pending": one("SELECT COUNT(*) FROM photos WHERE status='ok' AND stage_faces=0"),
        }
        cats = {r["category"]: r["n"] for r in con.execute("SELECT category, COUNT(*) n FROM events GROUP BY category")}
    d["categories"] = cats
    d["face_models_installed"] = mr.is_installed("yunet") and mr.is_installed("sface")
    d["target"] = selection.SelectionConfig.from_dict(p.db.get_setting("album_config")).target
    d["jobs"] = jm.list(5)
    d["last_analysis"] = p.db.get_setting("last_analysis")
    d["provider"] = ai_analysis.provider_settings(p.db)
    return d


# ---------------- jobs ----------------

@app.post("/api/projects/{pid}/analyze")
def analyze(pid: str, redo: Optional[str] = None) -> dict:
    p, jm = proj(pid)
    if not p.source_dir.is_dir():
        raise HTTPException(400, "The photo folder is not available (disconnected drive?).")
    if redo not in (None, "faces"):
        raise HTTPException(400, "redo must be 'faces'")
    if redo == "faces" and not (mr.is_installed("yunet") and mr.is_installed("sface")):
        raise HTTPException(400, "The face models are not installed. Approve them in AI & Privacy first.")
    jid = jm.submit("analyze", lambda ctx: run_analysis(p, ctx, redo_faces=redo == "faces"),
                    params={"redo": redo} if redo else None)
    return {"job_id": jid}


@app.get("/api/projects/{pid}/jobs")
def jobs(pid: str) -> list[dict]:
    _, jm = proj(pid)
    return jm.list(20)


@app.post("/api/projects/{pid}/jobs/{jid}/{action}")
def job_action(pid: str, jid: int, action: str) -> dict:
    _, jm = proj(pid)
    if action == "pause":
        jm.pause(jid)
    elif action == "resume":
        jm.resume(jid)
    elif action == "cancel":
        jm.cancel(jid)
    else:
        raise HTTPException(400, "unknown action")
    return {"ok": True}


# ---------------- photos ----------------

SORTS = {
    "time": "COALESCE(p.taken_ts, 1e18), p.rel_path",
    "name": "p.rel_path",
    "quality": "COALESCE(q.technical, 0) DESC",
    "score": "COALESCE(s.score, -1) DESC, COALESCE(q.technical,0) DESC",
}


@app.get("/api/projects/{pid}/photos")
def photos(
    pid: str,
    sort: str = "time",
    decision: Optional[str] = None,
    favorite: bool = False,
    in_album: Optional[bool] = None,
    category: Optional[str] = None,
    person_id: Optional[int] = None,
    min_rating: Optional[int] = None,
    issue: Optional[str] = None,
    group_id: Optional[int] = None,
    include_duplicates: bool = True,
) -> dict:
    p, _ = proj(pid)
    where = ["p.status='ok'"]
    args: list = []
    if decision == "undecided":
        where.append("u.decision IS NULL")
    elif decision in ("selected", "rejected"):
        where.append("u.decision=?")
        args.append(decision)
    if favorite:
        where.append("u.favorite=1")
    if in_album is True:
        where.append("(s.photo_id IS NOT NULL AND COALESCE(u.decision,'')!='rejected' OR u.decision='selected')")
    elif in_album is False:
        where.append("s.photo_id IS NULL AND COALESCE(u.decision,'')!='selected'")
    if category:
        where.append("e.category=?")
        args.append(category)
    if person_id is not None:
        where.append("p.id IN (SELECT photo_id FROM faces WHERE person_id=?)")
        args.append(person_id)
    if min_rating:
        where.append("u.rating>=?")
        args.append(min_rating)
    if group_id is not None:
        where.append("p.group_id=?")
        args.append(group_id)
    if not include_duplicates:
        where.append("p.duplicate_of IS NULL")
    if issue == "blurry":
        where.append("q.sharpness < 0.25")
    elif issue == "exposure":
        where.append("q.exposure < 0.35")
    elif issue == "closed_eyes":
        where.append("p.id IN (SELECT photo_id FROM faces WHERE eyes_closed=1 AND eyes_reliable=1)")
    order = SORTS.get(sort, SORTS["time"])
    sql = (
        "SELECT p.id, p.width, p.height, p.taken_at, p.group_id, p.duplicate_of, q.technical, q.sharpness, "
        "e.category, u.decision, u.favorite, u.rating, s.rank AS album_rank "
        "FROM photos p LEFT JOIN quality q ON q.photo_id=p.id LEFT JOIN events e ON e.photo_id=p.id "
        "LEFT JOIN user_state u ON u.photo_id=p.id LEFT JOIN selection s ON s.photo_id=p.id "
        f"WHERE {' AND '.join(where)} ORDER BY {order}"
    )
    with p.db.connect() as con:
        rows = con.execute(sql, args).fetchall()
    cols = ["id", "width", "height", "taken_at", "group_id", "duplicate_of", "technical", "sharpness", "category",
            "decision", "favorite", "rating", "album_rank"]
    return {"columns": cols, "rows": [[r[c] for c in cols] for r in rows], "count": len(rows)}


@app.get("/api/projects/{pid}/photos/{photo_id}")
def photo_detail(pid: str, photo_id: int) -> dict:
    p, _ = proj(pid)
    _, names, roles = selection.person_weights(p.db)
    with p.db.connect() as con:
        ph = con.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
        if not ph:
            raise HTTPException(404)
        d = dict(ph)
        q = con.execute("SELECT * FROM quality WHERE photo_id=?", (photo_id,)).fetchone()
        d["quality"] = dict(q) if q else None
        if d["quality"] and d["quality"].get("details"):
            d["quality"]["details"] = json.loads(d["quality"]["details"])
        d["faces"] = []
        for f in con.execute("SELECT * FROM faces WHERE photo_id=?", (photo_id,)):
            f = dict(f)
            f.pop("embedding", None)
            f["landmarks"] = json.loads(f["landmarks"] or "[]")
            f["excluded_person_ids"] = json.loads(f["excluded_person_ids"] or "[]")
            f["person_name"] = names.get(f["person_id"])
            f["person_role"] = roles.get(f["person_id"])
            d["faces"].append(f)
        e = con.execute("SELECT * FROM events WHERE photo_id=?", (photo_id,)).fetchone()
        d["event"] = dict(e) if e else None
        if d["event"] and d["event"].get("scores"):
            d["event"]["scores"] = json.loads(d["event"]["scores"])
        u = con.execute("SELECT * FROM user_state WHERE photo_id=?", (photo_id,)).fetchone()
        d["state"] = dict(u) if u else None
        s = con.execute("SELECT * FROM selection WHERE photo_id=?", (photo_id,)).fetchone()
        d["selection"] = {**dict(s), "reasons": json.loads(s["reasons"])} if s else None
        if d["group_id"] is not None:
            d["group_members"] = [r[0] for r in con.execute(
                "SELECT id FROM photos WHERE group_id=? AND status='ok' ORDER BY COALESCE(taken_ts,0), rel_path", (d["group_id"],))]
        ai = con.execute(
            "SELECT provider, model, result, created_at FROM ai_cache WHERE content_hash=? ORDER BY created_at DESC",
            (d["sha256"] or "",)).fetchall()
        d["ai_results"] = [{**dict(a), "result": json.loads(a["result"])} for a in ai]
    d["file_name"] = Path(d["rel_path"]).name
    return d


def _send(path: Path, max_age: int = 86400) -> FileResponse:
    if not path.exists():
        raise HTTPException(404, "Not generated yet")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": f"private, max-age={max_age}"})


@app.get("/api/projects/{pid}/photos/{photo_id}/thumb")
def thumb(pid: str, photo_id: int):
    p, _ = proj(pid)
    return _send(p.thumb_path(photo_id))


@app.get("/api/projects/{pid}/photos/{photo_id}/preview")
def preview(pid: str, photo_id: int):
    p, _ = proj(pid)
    return _send(p.preview_path(photo_id))


BROWSER_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


@app.get("/api/projects/{pid}/photos/{photo_id}/original")
def original(pid: str, photo_id: int):
    """Full-resolution original for zooming (browser-displayable formats only; others get the preview)."""
    p, _ = proj(pid)
    with p.db.connect() as con:
        r = con.execute("SELECT rel_path FROM photos WHERE id=?", (photo_id,)).fetchone()
    if not r:
        raise HTTPException(404)
    src = safe_join(p.source_dir, r["rel_path"])
    mt = BROWSER_TYPES.get(src.suffix.lower())
    if not mt or not src.is_file():
        return _send(p.preview_path(photo_id))
    return FileResponse(src, media_type=mt, headers={"Cache-Control": "private, max-age=3600"})


class StateBody(BaseModel):
    ids: list[int]
    decision: Optional[str] = Field(None, pattern="^(selected|rejected|none)$")
    favorite: Optional[bool] = None
    rating: Optional[int] = Field(None, ge=0, le=5)


@app.post("/api/projects/{pid}/photos/state")
def set_state(pid: str, body: StateBody) -> dict:
    p, _ = proj(pid)
    fields: dict = {}
    if body.decision is not None:
        fields["decision"] = None if body.decision == "none" else body.decision
    if body.favorite is not None:
        fields["favorite"] = int(body.favorite)
    if body.rating is not None:
        fields["rating"] = body.rating or None
    with p.db.tx() as con:
        for pid_ in body.ids:
            p.db.touch_user_state(con, pid_, **fields)
    return {"updated": len(body.ids)}


class CategoryBody(BaseModel):
    ids: list[int]
    category: str


@app.post("/api/projects/{pid}/photos/category")
def set_category(pid: str, body: CategoryBody) -> dict:
    p, _ = proj(pid)
    try:
        events.set_user_category(p.db, body.ids, body.category)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"updated": len(body.ids)}


@app.get("/api/categories")
def categories() -> dict:
    return {"categories": events.CATEGORY_LIST, "buckets": events.BUCKETS}


# ---------------- faces & people ----------------

@app.get("/api/projects/{pid}/faces/{face_id}/crop")
def face_crop(pid: str, face_id: int):
    p, _ = proj(pid)
    out = p.faces_dir / f"{face_id // 1000}" / f"{face_id}.jpg"
    if not out.exists():
        with p.db.connect() as con:
            f = con.execute("SELECT photo_id, x, y, w, h FROM faces WHERE id=?", (face_id,)).fetchone()
        if not f:
            raise HTTPException(404)
        try:
            with Image.open(p.preview_path(f["photo_id"])) as im:
                W, H = im.size
                m = 0.35
                x0 = max(0, int((f["x"] - f["w"] * m) * W)); y0 = max(0, int((f["y"] - f["h"] * m) * H))
                x1 = min(W, int((f["x"] + f["w"] * (1 + m)) * W)); y1 = min(H, int((f["y"] + f["h"] * (1 + m)) * H))
                crop = im.convert("RGB").crop((x0, y0, x1, y1))
                crop.thumbnail((256, 256))
                out.parent.mkdir(parents=True, exist_ok=True)
                crop.save(out, "JPEG", quality=85)
        except OSError:
            raise HTTPException(404)
    return _send(out)


@app.get("/api/projects/{pid}/persons")
def persons(pid: str) -> list[dict]:
    p, _ = proj(pid)
    with p.db.connect() as con:
        rows = con.execute(
            "SELECT pe.*, COUNT(DISTINCT f.photo_id) photo_count, COUNT(f.id) face_count, "
            "SUM(CASE WHEN f.uncertain=1 THEN 1 ELSE 0 END) uncertain_count, "
            "SUM(CASE WHEN f.assignment='user' THEN 1 ELSE 0 END) confirmed_count "
            "FROM persons pe LEFT JOIN faces f ON f.person_id=pe.id GROUP BY pe.id "
            "ORDER BY (pe.role IS NOT NULL) DESC, (pe.name IS NOT NULL) DESC, photo_count DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["sample_faces"] = [x[0] for x in con.execute(
                "SELECT id FROM faces WHERE person_id=? ORDER BY (assignment='user') DESC, det_score*size_px DESC LIMIT 6",
                (r["id"],))]
            out.append(d)
    return out


class PersonPatch(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(bride|groom|none)$")
    importance: Optional[str] = None
    hidden: Optional[bool] = None


@app.patch("/api/projects/{pid}/persons/{person_id}")
def patch_person(pid: str, person_id: int, body: PersonPatch) -> dict:
    p, _ = proj(pid)
    levels = selection.importance_levels(p.db)
    with p.db.tx() as con:
        if not con.execute("SELECT 1 FROM persons WHERE id=?", (person_id,)).fetchone():
            raise HTTPException(404)
        if body.name is not None:
            con.execute("UPDATE persons SET name=? WHERE id=?", (body.name.strip()[:80] or None, person_id))
        if body.role is not None:
            role = None if body.role == "none" else body.role
            con.execute("UPDATE persons SET role=? WHERE id=?", (role, person_id))
            if role:
                con.execute("UPDATE persons SET importance=? WHERE id=?", (role, person_id))
            # Naming someone the bride/groom confirms their current face group
            if role:
                con.execute("UPDATE faces SET assignment='user', uncertain=0 WHERE person_id=? AND assignment='auto' AND COALESCE(match_conf,1) >= 0.5", (person_id,))
        if body.importance is not None:
            if body.importance not in levels:
                raise HTTPException(400, "unknown importance level")
            con.execute("UPDATE persons SET importance=? WHERE id=?", (body.importance, person_id))
        if body.hidden is not None:
            con.execute("UPDATE persons SET hidden=? WHERE id=?", (int(body.hidden), person_id))
        con.execute("UPDATE persons SET user_touched=1 WHERE id=?", (person_id,))
    return {"ok": True}


@app.get("/api/projects/{pid}/persons/{person_id}/faces")
def person_faces(pid: str, person_id: int) -> list[dict]:
    p, _ = proj(pid)
    with p.db.connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT id, photo_id, det_score, match_conf, uncertain, assignment, eyes_closed, eyes_reliable, size_px "
            "FROM faces WHERE person_id=? ORDER BY uncertain DESC, match_conf ASC", (person_id,))]


@app.get("/api/projects/{pid}/faces/unassigned")
def unassigned_faces(pid: str, limit: int = 300) -> list[dict]:
    p, _ = proj(pid)
    with p.db.connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT f.id, f.photo_id, f.det_score, f.size_px FROM faces f JOIN photos p ON p.id=f.photo_id "
            "WHERE f.person_id IS NULL AND f.assignment!='ignored' AND p.status='ok' ORDER BY f.size_px DESC LIMIT ?", (limit,))]


class MergeBody(BaseModel):
    target_id: int
    source_ids: list[int]


@app.post("/api/projects/{pid}/persons/merge")
def merge(pid: str, body: MergeBody) -> dict:
    p, _ = proj(pid)
    try:
        clustering.merge_persons(p.db, body.target_id, body.source_ids)
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


class FacesBody(BaseModel):
    face_ids: list[int]
    person_id: Optional[int] = None
    new_person: bool = False
    action: str = Field("move", pattern="^(move|confirm|uncertain|certain|ignore)$")


@app.post("/api/projects/{pid}/faces")
def faces_action(pid: str, body: FacesBody) -> dict:
    p, _ = proj(pid)
    if body.action == "move":
        target = clustering.move_faces(p.db, body.face_ids, body.person_id, body.new_person)
        return {"person_id": target}
    if body.action == "confirm":
        clustering.confirm_faces(p.db, body.face_ids)
    elif body.action in ("uncertain", "certain"):
        clustering.mark_uncertain(p.db, body.face_ids, body.action == "uncertain")
    elif body.action == "ignore":
        clustering.ignore_faces(p.db, body.face_ids)
    return {"ok": True}


@app.post("/api/projects/{pid}/recluster")
def recluster(pid: str) -> dict:
    p, _ = proj(pid)
    return clustering.recluster(p.db).__dict__


@app.get("/api/projects/{pid}/importance-levels")
def get_levels(pid: str) -> dict:
    p, _ = proj(pid)
    return selection.importance_levels(p.db)


@app.put("/api/projects/{pid}/importance-levels")
def put_levels(pid: str, levels: dict = Body(...)) -> dict:
    p, _ = proj(pid)
    clean = {}
    for k, v in levels.items():
        key = "".join(ch for ch in str(k).lower() if ch.isalnum() or ch == "_")[:40]
        if not key:
            continue
        clean[key] = {"label": str(v.get("label", key))[:60], "weight": float(min(1, max(0, float(v.get("weight", 0.2))))),
                      "order": int(v.get("order", 99))}
    for required in ("bride", "groom", "other"):
        clean.setdefault(required, selection.DEFAULT_IMPORTANCE[required])
    p.db.set_setting("importance_levels", clean)
    return clean


# ---------------- review & compare ----------------

@app.get("/api/projects/{pid}/review")
def review_counts(pid: str) -> dict:
    p, _ = proj(pid)
    return {"queues": review.QUEUES, "counts": review.queue_counts(p.db)}


@app.get("/api/projects/{pid}/review/{kind}")
def review_queue(pid: str, kind: str, limit: int = 500) -> list[dict]:
    p, _ = proj(pid)
    try:
        return review.queue(p.db, kind, limit)
    except KeyError:
        raise HTTPException(404)


@app.post("/api/projects/{pid}/review/mark-reviewed")
def mark_reviewed(pid: str, body: dict = Body(...)) -> dict:
    p, _ = proj(pid)
    review.mark_reviewed(p.db, [int(i) for i in body.get("ids", [])])
    return {"ok": True}


@app.get("/api/projects/{pid}/compare/next")
def compare_next(pid: str, mode: str = "all", after: int = 0) -> dict:
    p, _ = proj(pid)
    g = review.next_group(p.db, mode, after)
    return {"group": g}


@app.get("/api/projects/{pid}/compare/group/{group_id}")
def compare_group(pid: str, group_id: int) -> dict:
    p, _ = proj(pid)
    return {"group": review.compare_group(p.db, group_id)}


class DecideBody(BaseModel):
    winner_id: int
    loser_ids: list[int]
    reject_losers: bool = False


@app.post("/api/projects/{pid}/compare/decide")
def compare_decide(pid: str, body: DecideBody) -> dict:
    p, _ = proj(pid)
    review.decide(p.db, body.winner_id, body.loser_ids, body.reject_losers)
    return {"ok": True}


# ---------------- album ----------------

@app.get("/api/projects/{pid}/album/config")
def album_config(pid: str) -> dict:
    p, _ = proj(pid)
    from dataclasses import asdict

    available = {b: 0 for b in events.BUCKETS}
    with p.db.connect() as con:
        for r in con.execute(
            "SELECT e.category, COUNT(*) n FROM photos p JOIN events e ON e.photo_id=p.id "
            "LEFT JOIN user_state u ON u.photo_id=p.id WHERE p.status='ok' "
            "AND (p.duplicate_of IS NULL OR u.decision='selected') "
            "AND COALESCE(u.decision, '') != 'rejected' GROUP BY e.category"):
            b = events.CATEGORY_TO_BUCKET.get(r["category"], "other")
            available[b] = available.get(b, 0) + r["n"]
    return {"config": asdict(selection.SelectionConfig.from_dict(p.db.get_setting("album_config"))),
            "defaults": asdict(selection.SelectionConfig()), "available": available}


@app.put("/api/projects/{pid}/album/config")
def put_album_config(pid: str, cfg: dict = Body(...)) -> dict:
    p, _ = proj(pid)
    from dataclasses import asdict

    c = selection.SelectionConfig.from_dict(cfg)
    c.target = min(max(1, c.target), 20000)
    p.db.set_setting("album_config", asdict(c))
    return asdict(c)


@app.post("/api/projects/{pid}/album/generate")
def album_generate(pid: str) -> dict:
    p, _ = proj(pid)
    return selection.generate(p.db)


@app.get("/api/projects/{pid}/album")
def album(pid: str) -> dict:
    p, _ = proj(pid)
    with p.db.connect() as con:
        run = con.execute("SELECT * FROM selection_runs ORDER BY id DESC LIMIT 1").fetchone()
        rows = con.execute(
            "SELECT s.photo_id, s.rank, s.score, s.bucket, s.reasons, u.decision FROM selection s "
            "LEFT JOIN user_state u ON u.photo_id=s.photo_id ORDER BY s.rank").fetchall()
        extra = [r[0] for r in con.execute(
            "SELECT photo_id FROM user_state WHERE decision='selected' AND photo_id NOT IN (SELECT photo_id FROM selection)")]
    return {
        "run": {**dict(run), "summary": json.loads(run["summary"]), "config": json.loads(run["config"])} if run else None,
        "items": [{"photo_id": r["photo_id"], "rank": r["rank"], "score": r["score"], "bucket": r["bucket"],
                   "decision": r["decision"], **json.loads(r["reasons"])} for r in rows],
        "selected_not_in_run": extra,
        "approved_count": len(export.approved_photo_ids(p.db)),
    }


@app.post("/api/projects/{pid}/album/replace/{photo_id}")
def album_replace(pid: str, photo_id: int) -> dict:
    """Reject a recommendation and suggest the best alternative from its similar group or moment."""
    p, _ = proj(pid)
    with p.db.tx() as con:
        p.db.touch_user_state(con, photo_id, decision="rejected")
    with p.db.connect() as con:
        g = con.execute("SELECT group_id FROM photos WHERE id=?", (photo_id,)).fetchone()
    alternatives = []
    if g and g["group_id"] is not None:
        grp = review.compare_group(p.db, g["group_id"])
        if grp:
            alternatives = [x["id"] for x in sorted(grp["photos"], key=lambda x: -x["score"])
                            if x["id"] != photo_id and x.get("decision") != "rejected"][:4]
    return {"rejected": photo_id, "alternatives": alternatives}


# ---------------- preferences ----------------

@app.get("/api/projects/{pid}/preferences")
def get_prefs(pid: str) -> dict:
    p, _ = proj(pid)
    return preferences.build(p.db).describe()


@app.post("/api/projects/{pid}/preferences/reset")
def reset_prefs(pid: str) -> dict:
    p, _ = proj(pid)
    preferences.reset(p.db)
    return preferences.build(p.db).describe()


# ---------------- AI providers ----------------

@app.get("/api/ai/providers")
def ai_providers() -> dict:
    out = []
    for pid in PROVIDER_IDS:
        prov = get_provider(pid)
        if prov:
            out.append(prov.capabilities().__dict__)
    return {"providers": out, "cloud_warning": CLOUD_WARNING, "pricing_as_of": pricing.PRICES_AS_OF,
            "pricing_url": pricing.PRICING_URL, "api_key_source": secrets.key_source(),
            "ollama": ollama_mod.server_status()}


@app.get("/api/projects/{pid}/ai")
def ai_settings(pid: str) -> dict:
    p, _ = proj(pid)
    s = ai_analysis.provider_settings(p.db)
    return {
        "provider": s,
        "consents": {k: has_consent(p.db, k) for k in ("anthropic_api", "claude_code")},
        "spending_limit_usd": p.db.get_setting("spending_limit_usd"),
        "spent_usd": {k: round(spent_usd(p.db, k), 4) for k in ("anthropic_api", "claude_code")},
    }


class ProviderBody(BaseModel):
    id: str
    model: str = ""
    options: dict = {}


@app.put("/api/projects/{pid}/ai/provider")
def set_provider(pid: str, body: ProviderBody) -> dict:
    p, _ = proj(pid)
    if body.id not in PROVIDER_IDS:
        raise HTTPException(400, "unknown provider")
    opts = {k: v for k, v in body.options.items() if k in ("image_size", "effort", "max_budget_usd_per_photo")}
    p.db.set_setting("ai_provider", {"id": body.id, "model": body.model[:100], "options": opts})
    return {"ok": True, "consent_needed": body.id in ("anthropic_api", "claude_code") and not has_consent(p.db, body.id)}


class ConsentBody(BaseModel):
    provider: str
    accepted: bool
    warning_text: str


@app.post("/api/projects/{pid}/ai/consent")
def consent(pid: str, body: ConsentBody) -> dict:
    p, _ = proj(pid)
    if body.provider not in ("anthropic_api", "claude_code"):
        raise HTTPException(400)
    if body.accepted and body.warning_text != CLOUD_WARNING:
        raise HTTPException(400, "Consent must be given to the current warning text.")
    record_consent(p.db, body.provider, body.accepted)
    return {"ok": True}


@app.put("/api/projects/{pid}/ai/spending-limit")
def spending_limit(pid: str, body: dict = Body(...)) -> dict:
    p, _ = proj(pid)
    v = body.get("limit_usd")
    p.db.set_setting("spending_limit_usd", None if v in (None, "") else max(0.0, float(v)))
    return {"spending_limit_usd": p.db.get_setting("spending_limit_usd")}


@app.get("/api/projects/{pid}/ai/estimate")
def ai_estimate(pid: str, scope: str = "album") -> dict:
    p, _ = proj(pid)
    return ai_analysis.estimate(p.db, scope)


class RunBody(BaseModel):
    scope: str = Field("album", pattern="^(album|uncategorized|all)$")
    confirm_upload: bool = False


@app.post("/api/projects/{pid}/ai/run")
def ai_run(pid: str, body: RunBody) -> dict:
    p, jm = proj(pid)
    prov = ai_analysis.build_provider(p.db)
    if prov is None:
        raise HTTPException(400, "Choose an AI provider first.")
    if prov.is_cloud:
        if not has_consent(p.db, prov.id):
            raise ConsentRequired("Consent required before uploading photos.")
        if not body.confirm_upload:
            raise HTTPException(400, "Please confirm the upload and estimated cost.")
    jid = jm.submit("ai", lambda ctx: ai_analysis.run_ai(p, ctx), {"scope": body.scope})
    return {"job_id": jid}


@app.get("/api/projects/{pid}/ai/usage")
def ai_usage(pid: str) -> dict:
    p, _ = proj(pid)
    with p.db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT provider, model, cost_basis, COUNT(*) requests, SUM(input_tokens) input_tokens, "
            "SUM(output_tokens) output_tokens, SUM(cost_usd) cost_usd FROM usage_log GROUP BY provider, model, cost_basis")]
    return {"usage": rows, "note": "Costs are computed from token usage reported by each API response and list prices; "
                                   "your Anthropic invoice is authoritative."}


@app.post("/api/projects/{pid}/ai/test")
def ai_test(pid: str) -> dict:
    """Send ONE synthetic, non-personal test image to the configured provider."""
    p, _ = proj(pid)
    prov = ai_analysis.build_provider(p.db)
    if prov is None:
        raise HTTPException(400, "Choose an AI provider first.")
    from .providers.base import ImageInput, require_consent
    import io

    require_consent(p.db, prov)
    img = Image.new("RGB", (256, 256), (240, 230, 220))
    for x in range(256):
        for y in range(0, 256, 32):
            img.putpixel((x, y), (180, 150, 120))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    t = time.time()
    res = prov.analyze_image(ImageInput(0, "test", buf.getvalue(), 256, 256))
    return {"ok": True, "seconds": round(time.time() - t, 2), "result": json.loads(res.result_json()),
            "cost_usd": res.cost_usd, "cost_basis": res.cost_basis}


class KeyBody(BaseModel):
    key: str


@app.put("/api/secrets/anthropic")
def set_key(body: KeyBody) -> dict:
    try:
        where = secrets.set_anthropic_key(body.key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"stored_in": where}


@app.delete("/api/secrets/anthropic")
def delete_key() -> dict:
    secrets.delete_anthropic_key()
    return {"ok": True, "source": secrets.key_source()}


_pulls: dict[str, dict] = {}


@app.get("/api/ollama")
def ollama_info() -> dict:
    return {"status": ollama_mod.server_status(), "models": ollama_mod.list_models(), "pulls": _pulls}


class PullBody(BaseModel):
    model: str
    approved: bool = False


@app.post("/api/ollama/pull")
def ollama_pull(body: PullBody) -> dict:
    if not body.approved:
        raise HTTPException(400, "Model downloads require explicit approval.")
    if not all(ch.isalnum() or ch in ":-._/" for ch in body.model) or len(body.model) > 100:
        raise HTTPException(400, "invalid model name")

    def run() -> None:
        _pulls[body.model] = {"status": "starting"}
        try:
            for ev in ollama_mod.pull(body.model):
                _pulls[body.model] = {"status": ev.get("status"), "completed": ev.get("completed"), "total": ev.get("total")}
            _pulls[body.model] = {"status": "success"}
        except Exception as e:
            _pulls[body.model] = {"status": "error", "error": str(e)[:200]}

    threading.Thread(target=run, daemon=True).start()
    return {"started": body.model}


# ---------------- export ----------------

class ExportBody(BaseModel):
    destination: str
    category_subfolders: bool = False
    mode: str = Field("album", pattern="^(album|selected_only)$")


@app.post("/api/projects/{pid}/export/preview")
def export_preview(pid: str, body: ExportBody) -> dict:
    p, _ = proj(pid)
    dest = export.validate_destination(body.destination, p.source_dir)
    ids = export.approved_photo_ids(p.db, body.mode)
    with p.db.connect() as con:
        rows = con.execute(
            f"SELECT id, rel_path, size FROM photos WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall() if ids else []
    missing = [r["id"] for r in rows if not (p.source_dir / r["rel_path"]).is_file()]
    total = sum(r["size"] for r in rows)
    free = shutil.disk_usage(dest if dest.exists() else dest.parent).free
    return {"destination": str(dest), "count": len(ids), "bytes": total, "free_bytes": free,
            "enough_space": free > total * 1.05, "missing": missing}


@app.post("/api/projects/{pid}/export")
def export_run(pid: str, body: ExportBody) -> dict:
    p, jm = proj(pid)
    dest = export.validate_destination(body.destination, p.source_dir)
    ids = export.approved_photo_ids(p.db, body.mode)

    def job(ctx: JobContext) -> dict:
        ctx.progress(stage="export", done=0, total=len(ids), message="Copying originals…", force=True)
        rep = export.export_selection(p.db, p.source_dir, dest, ids, body.category_subfolders,
                                      progress=lambda n, t: ctx.progress(done=n, total=t), should_stop=ctx.should_stop)
        p.db.set_setting("last_export", rep)
        return {"exported": rep["exported"], "missing": len(rep["missing"]), "failed": len(rep["failed"]),
                "destination": rep["destination"]}

    return {"job_id": jm.submit("export", job, {"destination": str(dest)})}


@app.get("/api/projects/{pid}/export/last")
def export_last(pid: str) -> dict:
    p, _ = proj(pid)
    return {"report": p.db.get_setting("last_export")}


@app.post("/api/pick-export-folder")
def pick_export_folder() -> dict:
    return {"path": pick_folder("Choose an empty folder for the album export")}


# ---------------- privacy ----------------

@app.post("/api/projects/{pid}/privacy/{what}")
def privacy(pid: str, what: str) -> dict:
    p, _ = proj(pid)
    if what == "delete-faces":
        with p.db.tx() as con:
            con.execute("DELETE FROM faces")
            con.execute("DELETE FROM persons")
            con.execute("UPDATE photos SET stage_faces=0")
        shutil.rmtree(p.faces_dir, ignore_errors=True)
        p.faces_dir.mkdir(parents=True, exist_ok=True)
        return {"deleted": "faces, face descriptors and people"}
    if what == "delete-ai-results":
        with p.db.tx() as con:
            con.execute("DELETE FROM ai_cache")
            con.execute("DELETE FROM events WHERE source='vlm'")
        return {"deleted": "AI analysis results"}
    if what == "delete-embeddings":
        with p.db.tx() as con:
            con.execute("DELETE FROM embeddings")
            con.execute("UPDATE photos SET stage_embed=0")
        return {"deleted": "image embeddings"}
    if what == "delete-thumbnails":
        for d in (p.thumbs, p.previews, p.faces_dir):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
        with p.db.tx() as con:
            con.execute("UPDATE photos SET stage_media=0")
        return {"deleted": "thumbnails and previews (re-run analysis to regenerate)"}
    raise HTTPException(404)


# ---------------- frontend ----------------

def mount_frontend() -> None:
    dist = config.frontend_dist()
    if not (dist / "index.html").exists():
        @app.get("/")
        def no_frontend() -> HTMLResponse:
            resp = HTMLResponse("<h1>Wedding Album Curator</h1><p>The frontend has not been built. "
                                "Run <code>scripts/install.sh</code>.</p>")
            set_session(resp)
            return resp
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> Response:
        if full_path.startswith("api/"):
            raise HTTPException(404)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        resp = FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})
        set_session(resp)
        return resp
