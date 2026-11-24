"""Export the approved selection as byte-identical copies of the originals.

- Originals are only read; copies are verified against the indexed SHA-256.
- The destination must be a new or empty folder, outside the source folder.
- A manifest (CSV + JSON) records every exported and every missing file.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

from .db import ProjectDB
from .imaging import sha256_file
from .scanner import PathError, safe_join


def validate_destination(raw: str, source_root: Path) -> Path:
    if not raw or "\x00" in raw:
        raise PathError("Destination path is empty or invalid.")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise PathError("Please provide an absolute destination path.")
    p = p.resolve()
    src = source_root.resolve()
    if p == src or src in p.parents:
        raise PathError("The export folder must not be inside the original photos folder.")
    if p.exists():
        if not p.is_dir():
            raise PathError("Destination exists and is not a folder.")
        if any(p.iterdir()):
            raise PathError("Destination folder is not empty. Choose a new or empty folder.")
    else:
        if not p.parent.exists():
            raise PathError("The parent of the destination folder does not exist.")
    return p


def approved_photo_ids(db: ProjectDB, mode: str = "album") -> list[int]:
    """album = AI recommendations not rejected + everything the user selected."""
    with db.connect() as con:
        if mode == "selected_only":
            q = "SELECT photo_id FROM user_state WHERE decision='selected'"
        else:
            q = (
                "SELECT s.photo_id FROM selection s LEFT JOIN user_state u ON u.photo_id=s.photo_id "
                "WHERE COALESCE(u.decision,'') != 'rejected' "
                "UNION SELECT photo_id FROM user_state WHERE decision='selected'"
            )
        return [r[0] for r in con.execute(q)]


def _unique_name(dest_dir: Path, name: str, used: set[str]) -> Path:
    stem, suffix = os.path.splitext(name)
    candidate = name
    i = 1
    while candidate.lower() in used or (dest_dir / candidate).exists():
        candidate = f"{stem}_{i}{suffix}"
        i += 1
    used.add(candidate.lower())
    return dest_dir / candidate


def export_selection(
    db: ProjectDB,
    source_root: Path,
    dest: Path,
    photo_ids: list[int],
    category_subfolders: bool = False,
    verify: bool = True,
    progress: Optional[Callable[[int, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    with db.connect() as con:
        rows = {
            r["id"]: dict(r)
            for r in con.execute(
                f"SELECT p.id, p.rel_path, p.sha256, p.taken_at, e.category FROM photos p "
                f"LEFT JOIN events e ON e.photo_id=p.id WHERE p.id IN ({','.join('?' * len(photo_ids))})",
                photo_ids,
            )
        } if photo_ids else {}
    ordered = sorted(rows.values(), key=lambda r: (r["taken_at"] or "", r["rel_path"]))
    used: dict[Path, set[str]] = {}
    exported, missing, failed = [], [], []
    for n, r in enumerate(ordered, 1):
        if should_stop and should_stop():
            break
        try:
            src = safe_join(source_root, r["rel_path"])
        except PathError:
            failed.append({"photo_id": r["id"], "source": r["rel_path"], "error": "invalid path"})
            continue
        sub = dest / (r["category"] or "other") if category_subfolders else dest
        sub.mkdir(exist_ok=True)
        if not src.is_file():
            missing.append({"photo_id": r["id"], "source": r["rel_path"]})
            continue
        target = _unique_name(sub, src.name, used.setdefault(sub, set()))
        try:
            shutil.copy2(src, target)  # byte-for-byte copy, preserves timestamps
            if verify and r["sha256"]:
                digest = sha256_file(target)
                if digest != r["sha256"]:
                    target.unlink(missing_ok=True)
                    failed.append({"photo_id": r["id"], "source": r["rel_path"],
                                   "error": "checksum mismatch (original changed since indexing?)"})
                    continue
            exported.append({
                "photo_id": r["id"], "source": r["rel_path"], "exported_as": str(target.relative_to(dest)),
                "sha256": r["sha256"], "category": r["category"], "taken_at": r["taken_at"],
            })
        except OSError as e:
            failed.append({"photo_id": r["id"], "source": r["rel_path"], "error": str(e)[:200]})
        if progress:
            progress(n, len(ordered))

    report = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "destination": str(dest),
        "requested": len(photo_ids),
        "exported": len(exported),
        "missing": missing,
        "failed": failed,
        "verified_checksums": verify,
    }
    (dest / "album_manifest.json").write_text(json.dumps({**report, "files": exported}, indent=2, ensure_ascii=False))
    with open(dest / "album_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["photo_id", "source", "exported_as", "sha256", "category", "taken_at"])
        w.writeheader()
        w.writerows(exported)
    return report
