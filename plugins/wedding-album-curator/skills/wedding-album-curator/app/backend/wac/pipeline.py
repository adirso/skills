"""The analysis pipeline: scan -> media/quality/faces -> embeddings -> grouping/people/moments.

Each per-photo stage is tracked with a flag, so analysis is incremental and restart-safe:
re-running only processes new, changed or not-yet-analyzed photos. Models that are not
installed are skipped and the corresponding flag stays 0 until they are.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from PIL import Image

from . import clustering, config, embeddings, events, faces, models_registry as mr, similarity
from .db import ProjectDB, to_blob
from .imaging import ImageError, open_image, phash, save_jpeg, sha256_file, to_bgr
from .jobs import JobContext
from .quality import analyze_quality
from .scanner import safe_join, scan_folder


class Project:
    def __init__(self, pid: str, name: str, source_dir: Path, root: Path):
        self.id = pid
        self.name = name
        self.source_dir = Path(source_dir)
        self.root = root
        self.db = ProjectDB(root / "project.db")
        self.thumbs = root / "cache" / "thumbs"
        self.previews = root / "cache" / "previews"
        self.faces_dir = root / "cache" / "faces"
        for d in (self.thumbs, self.previews, self.faces_dir):
            d.mkdir(parents=True, exist_ok=True)

    def thumb_path(self, photo_id: int) -> Path:
        return self.thumbs / f"{photo_id // 1000}" / f"{photo_id}.jpg"

    def preview_path(self, photo_id: int) -> Path:
        return self.previews / f"{photo_id // 1000}" / f"{photo_id}.jpg"


CHUNK = 64  # photos per batch between progress/pause/cancel checks


def _workers() -> int:
    return max(1, min(6, (os.cpu_count() or 2) - 2))


def process_photo(project: Project, row: dict, face_models: bool) -> dict:
    """Decode once and compute everything per-photo. Returns DB updates (no writes here)."""
    pid = row["id"]
    out: dict = {"id": pid}
    img: Optional[Image.Image] = None
    if not row["stage_media"]:
        src = safe_join(project.source_dir, row["rel_path"])
        try:
            dec = open_image(src, config.PREVIEW_SIZE)
        except ImageError as e:
            return {"id": pid, "error": str(e)}
        img = dec.image
        save_jpeg(img, project.preview_path(pid), config.PREVIEW_SIZE, quality=88)
        save_jpeg(img, project.thumb_path(pid), config.THUMB_SIZE, quality=82)
        out["media"] = {
            "sha256": sha256_file(src), "phash": phash(img), "width": dec.width, "height": dec.height,
            "taken_at": dec.taken_at, "taken_ts": dec.taken_ts, "camera": dec.camera, "format": dec.format,
        }
    need_faces = face_models and not row["stage_faces"]
    need_quality = not row["stage_quality"] or need_faces
    if need_quality or need_faces:
        if img is None:
            try:
                with Image.open(project.preview_path(pid)) as im:
                    img = im.convert("RGB")
            except (OSError, ValueError):
                return {"id": pid, "redo_media": True}
        bgr = to_bgr(img)
        face_list = None
        if need_faces:
            an = faces.get_analyzer()
            width = (out.get("media") or {}).get("width") or row.get("width") or img.width
            face_list = an.analyze(bgr, width) if an else None
            out["faces"] = face_list
        boxes = [f.box for f in face_list] if face_list is not None else row.get("_face_boxes")
        out["quality"] = analyze_quality(bgr, boxes)
    return out


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _match_old_face(box, old: list[dict]) -> Optional[dict]:
    """Best-overlapping previous face (IoU >= 0.5); each old face is used at most once."""
    best, best_iou = None, 0.5
    for o in old:
        if o.get("_used"):
            continue
        v = _iou(box, (o["x"], o["y"], o["w"], o["h"]))
        if v >= best_iou:
            best, best_iou = o, v
    if best is not None:
        best["_used"] = True
    return best


def write_result(db: ProjectDB, res: dict, face_models: bool) -> None:
    pid = res["id"]
    with db.tx() as con:
        if "error" in res:
            con.execute("UPDATE photos SET status='error', error=? WHERE id=?", (res["error"][:300], pid))
            return
        if res.get("redo_media"):
            con.execute("UPDATE photos SET stage_media=0 WHERE id=?", (pid,))
            return
        m = res.get("media")
        if m:
            con.execute(
                "UPDATE photos SET sha256=?, phash=?, width=?, height=?, taken_at=?, taken_ts=?, camera=?, format=?, "
                "status='ok', error=NULL, stage_media=1 WHERE id=?",
                (m["sha256"], m["phash"], m["width"], m["height"], m["taken_at"], m["taken_ts"], m["camera"], m["format"], pid),
            )
        if "faces" in res and res["faces"] is not None:
            # Re-detection: carry each old face's person and user corrections over to the new
            # face at the same position, so names, roles and fixes survive a re-scan.
            old = [dict(r) for r in con.execute(
                "SELECT x, y, w, h, person_id, assignment, excluded_person_ids FROM faces WHERE photo_id=?", (pid,))]
            con.execute("DELETE FROM faces WHERE photo_id=?", (pid,))
            for f in res["faces"]:
                prev = _match_old_face(f.box, old)
                cur = con.execute(
                    "INSERT INTO faces(photo_id, x, y, w, h, det_score, size_px, landmarks, embedding, sharpness, frontal, "
                    "eye_blink_left, eye_blink_right, eyes_closed, eyes_reliable, landmarker_found, edge_cut) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, *f.box, f.det_score, f.size_px, json.dumps(f.landmarks),
                     to_blob(f.embedding) if f.embedding is not None else None, f.sharpness, f.frontal,
                     f.blink_left, f.blink_right, None if f.eyes_closed is None else int(f.eyes_closed),
                     int(f.eyes_reliable), None if f.landmarker_found is None else int(f.landmarker_found), int(f.edge_cut)),
                )
                if prev:
                    con.execute("UPDATE faces SET person_id=?, assignment=?, excluded_person_ids=? WHERE id=?",
                                (prev["person_id"], prev["assignment"], prev["excluded_person_ids"], cur.lastrowid))
            con.execute("UPDATE photos SET stage_faces=1 WHERE id=?", (pid,))
        q = res.get("quality")
        if q is not None:
            con.execute(
                "INSERT INTO quality(photo_id, sharpness, exposure, brightness, highlights_clipped, shadows_clipped, contrast, "
                "noise, colorfulness, composition, technical, details) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(photo_id) DO UPDATE SET sharpness=excluded.sharpness, exposure=excluded.exposure, "
                "brightness=excluded.brightness, highlights_clipped=excluded.highlights_clipped, "
                "shadows_clipped=excluded.shadows_clipped, contrast=excluded.contrast, noise=excluded.noise, "
                "colorfulness=excluded.colorfulness, composition=excluded.composition, technical=excluded.technical, "
                "details=excluded.details",
                (pid, q.sharpness, q.exposure, q.brightness, q.highlights_clipped, q.shadows_clipped, q.contrast,
                 q.noise, q.colorfulness, q.composition, q.technical, json.dumps(q.details)),
            )
            con.execute("UPDATE photos SET stage_quality=1 WHERE id=?", (pid,))


def run_analysis(project: Project, ctx: JobContext, redo_faces: bool = False) -> dict:
    """Incremental analysis. `redo_faces` re-detects faces in every photo (user corrections
    and person names are carried over by face position)."""
    db = project.db
    if redo_faces and mr.is_installed("yunet") and mr.is_installed("sface"):
        with db.tx() as con:
            con.execute("UPDATE photos SET stage_faces=0 WHERE status='ok'")
    timings: dict = {}
    t0 = time.time()

    # 1. Scan
    ctx.progress(stage="scan", done=0, total=0, message="Scanning folder…", force=True)
    scan = scan_folder(db, project.source_dir, progress=lambda n: ctx.progress(done=n, message=f"Found {n} photos"),
                       should_stop=ctx.should_stop)
    ctx.check()
    timings["scan_s"] = round(time.time() - t0, 2)

    # 2. Per-photo media + quality + faces
    face_models = mr.is_installed("yunet") and mr.is_installed("sface")
    if face_models:
        faces.reset_analyzers()
    with db.connect() as con:
        cond = "stage_media=0 OR stage_quality=0" + (" OR stage_faces=0" if face_models else "")
        todo = [dict(r) for r in con.execute(
            f"SELECT id, rel_path, width, stage_media, stage_quality, stage_faces FROM photos "
            f"WHERE status IN ('pending','ok') AND ({cond}) ORDER BY id")]
        if todo:
            boxes: dict[int, list] = {}
            for r in con.execute("SELECT photo_id, x, y, w, h FROM faces"):
                boxes.setdefault(r["photo_id"], []).append((r["x"], r["y"], r["w"], r["h"]))
            for r in todo:
                if r["stage_faces"]:
                    r["_face_boxes"] = boxes.get(r["id"], [])
    t1 = time.time()
    total = len(todo)
    ctx.progress(stage="analyze", done=0, total=total, message="Analyzing photos…", force=True)
    errors = 0
    done = 0
    chunk = CHUNK
    with ThreadPoolExecutor(max_workers=_workers()) as pool:
        for start in range(0, total, chunk):
            ctx.check()
            batch = todo[start:start + chunk]
            for res in pool.map(lambda r: process_photo(project, r, face_models), batch):
                write_result(db, res, face_models)
                errors += 1 if "error" in res else 0
                done += 1
            rate = done / max(time.time() - t1, 1e-6)
            ctx.progress(done=done, message=f"{done}/{total} photos · {rate:.1f} photos/s")
    timings["analyze_s"] = round(time.time() - t1, 2)
    timings["analyze_photos"] = total
    timings["analyze_rate"] = round(total / max(time.time() - t1, 1e-6), 2) if total else None

    # 3. Embeddings
    t2 = time.time()
    n_emb = 0
    if embeddings.available():
        with db.connect() as con:
            ids = [r[0] for r in con.execute("SELECT id FROM photos WHERE status='ok' AND stage_embed=0 ORDER BY id")]
        ctx.progress(stage="embed", done=0, total=len(ids), message="Computing visual embeddings…", force=True)
        bs = 32
        for start in range(0, len(ids), bs):
            ctx.check()
            batch_ids = ids[start:start + bs]
            imgs, ok_ids = [], []
            for pid in batch_ids:
                try:
                    with Image.open(project.preview_path(pid)) as im:
                        im.thumbnail((448, 448))
                        imgs.append(im.convert("RGB"))
                        ok_ids.append(pid)
                except OSError:
                    continue
            if imgs:
                vecs = embeddings.embed_images(imgs)
                with db.tx() as con:
                    for pid, v in zip(ok_ids, vecs):
                        con.execute(
                            "INSERT OR REPLACE INTO embeddings(photo_id, model, vector) VALUES (?,?,?)",
                            (pid, embeddings.MODEL_NAME, to_blob(v)),
                        )
                        con.execute("UPDATE photos SET stage_embed=1 WHERE id=?", (pid,))
            n_emb += len(ok_ids)
            ctx.progress(done=min(start + bs, len(ids)))
    timings["embed_s"] = round(time.time() - t2, 2)
    timings["embed_photos"] = n_emb

    # 4. Global post-processing (fast)
    ctx.check()
    ctx.progress(stage="organize", done=0, total=4, message="Finding duplicates and similar shots…", force=True)
    t3 = time.time()
    dups = similarity.mark_exact_duplicates(db)
    groups = similarity.compute_groups(db)
    ctx.progress(done=2, message="Grouping people…", force=True)
    people = clustering.recluster(db) if face_models else None
    ctx.progress(done=3, message="Recognizing wedding moments…", force=True)
    moments = events.classify_all(db)
    timings["organize_s"] = round(time.time() - t3, 2)
    timings["total_s"] = round(time.time() - t0, 2)

    result = {
        "scan": scan.__dict__,
        "processed": total,
        "errors": errors,
        "exact_duplicates": dups,
        "similar_groups": groups,
        "people": people.__dict__ if people else {"skipped": "face models not installed"},
        "moments": moments,
        "embeddings": n_emb if embeddings.available() else "skipped: CLIP model not installed",
        "timings": timings,
    }
    db.set_setting("last_analysis", {"finished_at": time.time(), **result})
    bench = db.get_setting("benchmarks", [])
    bench.append({"at": time.time(), **timings})
    db.set_setting("benchmarks", bench[-20:])
    ctx.progress(stage="done", done=4, total=4, message="Analysis complete", force=True)
    return result
