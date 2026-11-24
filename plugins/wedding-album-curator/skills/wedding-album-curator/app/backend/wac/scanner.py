"""Recursive, incremental folder scanning.

Only regular files inside the authorized source folder are indexed. Symlinks are not
followed (a link could point outside the folder the user authorized).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

from . import config
from .db import ProjectDB


class PathError(ValueError):
    pass


def validate_source_dir(raw: str) -> Path:
    """Validate a user-supplied folder path. Returns the resolved absolute path."""
    if not raw or "\x00" in raw:
        raise PathError("Folder path is empty or invalid.")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise PathError("Please provide an absolute folder path.")
    try:
        p = p.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise PathError(f"Folder does not exist: {raw}") from e
    if not p.is_dir():
        raise PathError("Path is not a folder.")
    if not os.access(p, os.R_OK | os.X_OK):
        raise PathError("Folder is not readable.")
    if p == Path(p.anchor):
        raise PathError("Refusing to index an entire drive root; please choose the photo folder.")
    return p


def safe_join(root: Path, rel_path: str) -> Path:
    """Resolve rel_path under root, refusing anything that escapes the root."""
    if "\x00" in rel_path or os.path.isabs(rel_path):
        raise PathError("invalid relative path")
    candidate = (root / rel_path).resolve()
    root_r = root.resolve()
    if candidate != root_r and root_r not in candidate.parents:
        raise PathError("path escapes the project folder")
    return candidate


def iter_image_files(root: Path) -> Iterator[tuple[str, os.stat_result]]:
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            if e.name.startswith("."):
                continue
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    stack.append(Path(e.path))
                    continue
                if not e.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if Path(e.name).suffix.lower() not in config.SUPPORTED_EXTENSIONS:
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            rel = os.path.relpath(e.path, root)
            yield rel.replace(os.sep, "/"), st


@dataclass
class ScanResult:
    found: int = 0
    added: int = 0
    changed: int = 0
    unchanged: int = 0
    missing: int = 0
    restored: int = 0
    skipped_large: int = 0
    errors: list[str] = field(default_factory=list)


def scan_folder(
    db: ProjectDB,
    root: Path,
    progress: Optional[Callable[[int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> ScanResult:
    """Index files under root. New/changed files are queued for processing (stage flags reset)."""
    res = ScanResult()
    with db.connect() as con:
        existing = {
            r["rel_path"]: (r["id"], r["size"], r["mtime"], r["status"])
            for r in con.execute("SELECT id, rel_path, size, mtime, status FROM photos")
        }
    seen: set[str] = set()
    batch_new: list[tuple] = []
    batch_changed: list[tuple] = []
    batch_restored: list[int] = []
    now = time.time()

    def flush() -> None:
        if not (batch_new or batch_changed or batch_restored):
            return
        with db.tx() as con:
            con.executemany(
                "INSERT INTO photos(rel_path, size, mtime, status, created_at) VALUES (?,?,?, 'pending', ?)",
                batch_new,
            )
            con.executemany(
                "UPDATE photos SET size=?, mtime=?, status='pending', error=NULL, sha256=NULL, phash=NULL, "
                "stage_media=0, stage_quality=0, stage_faces=0, stage_embed=0 WHERE id=?",
                batch_changed,
            )
            # The file came back unchanged: restore its previous state.
            con.executemany(
                "UPDATE photos SET status=CASE WHEN stage_media=1 THEN 'ok' ELSE 'pending' END WHERE id=?",
                [(i,) for i in batch_restored],
            )
            # Changed files: drop derived data so it is recomputed.
            for size, mtime, pid in batch_changed:
                con.execute("DELETE FROM faces WHERE photo_id=?", (pid,))
                con.execute("DELETE FROM quality WHERE photo_id=?", (pid,))
                con.execute("DELETE FROM embeddings WHERE photo_id=?", (pid,))
                con.execute("DELETE FROM events WHERE photo_id=? AND source!='user'", (pid,))
        batch_new.clear()
        batch_changed.clear()
        batch_restored.clear()

    for rel, st in iter_image_files(root):
        if should_stop and should_stop():
            break
        res.found += 1
        seen.add(rel)
        if st.st_size > config.MAX_FILE_BYTES:
            res.skipped_large += 1
            continue
        prev = existing.get(rel)
        if prev is None:
            batch_new.append((rel, st.st_size, st.st_mtime, now))
            res.added += 1
        else:
            pid, size, mtime, status = prev
            if size != st.st_size or abs(mtime - st.st_mtime) > 1e-3:
                batch_changed.append((st.st_size, st.st_mtime, pid))
                res.changed += 1
            elif status == "missing":
                batch_restored.append(pid)
                res.restored += 1
            else:
                res.unchanged += 1
        if len(batch_new) + len(batch_changed) >= 500:
            flush()
        if progress and res.found % 200 == 0:
            progress(res.found)
    flush()

    if not (should_stop and should_stop()):
        missing = [pid for rel, (pid, _, _, status) in existing.items() if rel not in seen and status != "missing"]
        if missing:
            with db.tx() as con:
                con.executemany("UPDATE photos SET status='missing' WHERE id=?", [(m,) for m in missing])
        res.missing = len(missing)
    if progress:
        progress(res.found)
    return res
