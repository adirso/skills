"""Folder scanning, metadata, safety and duplicate detection."""
import os
from pathlib import Path

import pytest
from PIL import Image

from wac import imaging, similarity
from wac.scanner import PathError, iter_image_files, safe_join, scan_folder, validate_source_dir
from tests.conftest import run_job


def test_scan_is_recursive_and_filters_types(project):
    p, manifest = project
    res = scan_folder(p.db, p.source_dir)
    files = {rel for rel, _ in iter_image_files(p.source_dir)}
    assert "notes.txt" not in files
    assert any(f.startswith("backup/") for f in files)
    assert res.added == len(files) and res.added > 30


def test_symlinks_are_not_followed(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    Image.new("RGB", (10, 10)).save(outside / "secret.jpg")
    os.symlink(outside, root / "link")
    os.symlink(outside / "secret.jpg", root / "secret_link.jpg")
    assert list(iter_image_files(root)) == []


def test_incremental_scan_detects_add_change_missing_restore(project):
    p, manifest = project
    scan_folder(p.db, p.source_dir)
    again = scan_folder(p.db, p.source_dir)
    assert again.added == 0 and again.changed == 0
    target = p.source_dir / manifest["files"][1]
    data = target.read_bytes()
    Image.new("RGB", (50, 50), "red").save(p.source_dir / "new.jpg")
    target.write_bytes(data + b"\x00")  # change size
    moved = p.source_dir / manifest["files"][2]
    tmp = moved.with_suffix(".bak")
    moved.rename(tmp)
    r = scan_folder(p.db, p.source_dir)
    assert (r.added, r.changed, r.missing) == (1, 1, 1)
    tmp.rename(moved)
    r = scan_folder(p.db, p.source_dir)
    assert r.restored == 1


def test_safe_join_blocks_escape(tmp_path):
    with pytest.raises(PathError):
        safe_join(tmp_path, "../etc/passwd")
    with pytest.raises(PathError):
        safe_join(tmp_path, "/etc/passwd")
    assert safe_join(tmp_path, "a/b.jpg") == (tmp_path / "a/b.jpg").resolve()


def test_validate_source_dir(tmp_path):
    with pytest.raises(PathError):
        validate_source_dir("relative/path")
    with pytest.raises(PathError):
        validate_source_dir(str(tmp_path / "nope"))
    with pytest.raises(PathError):
        validate_source_dir("/")
    assert validate_source_dir(str(tmp_path)) == tmp_path.resolve()


def test_exif_metadata_and_orientation(sample_dir):
    src, manifest = sample_dir
    d = imaging.open_image(src / manifest["rotated"][0])
    # stored 900x600 with orientation 6 -> displayed portrait
    assert (d.width, d.height) == (600, 900)
    assert d.image.height > d.image.width
    assert d.taken_at and d.taken_at.startswith("2025-06-12")


def test_all_formats_decode(sample_dir):
    src, manifest = sample_dir
    for ext, rel in manifest["formats"].items():
        d = imaging.open_image(src / rel)
        assert d.image.mode == "RGB", ext


def test_corrupt_and_bomb_images_are_rejected(sample_dir, monkeypatch, tmp_path):
    src, manifest = sample_dir
    with pytest.raises(imaging.ImageError):
        imaging.open_image(src / manifest["corrupt"][0])
    big = tmp_path / "big.png"
    Image.new("RGB", (200, 200)).save(big)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(imaging.ImageError):
        imaging.open_image(big)


def test_exif_datetime_parsing_is_defensive():
    assert imaging.parse_exif_datetime("2024:05:01 10:11:12").year == 2024
    assert imaging.parse_exif_datetime("0000:00:00 00:00:00") is None
    assert imaging.parse_exif_datetime(b"garbage\x00\x01") is None
    assert imaging.parse_exif_datetime("1900:01:01 00:00:00") is None  # unrealistic clock


def test_duplicates_and_bursts(project):
    from wac.pipeline import run_analysis

    p, manifest = project
    run_job(p, run_analysis)
    with p.db.connect() as con:
        ids = {r["rel_path"]: dict(r) for r in con.execute("SELECT id, rel_path, duplicate_of, group_id, status FROM photos")}
    a, b = manifest["exact_duplicates"][0]
    # the copy indexed first is canonical; the other points to it
    assert {ids[a]["duplicate_of"], ids[b]["duplicate_of"]} == {None, min(ids[a]["id"], ids[b]["id"])}
    for burst in manifest["bursts"]:
        groups = {ids[f]["group_id"] for f in burst}
        assert len(groups) == 1 and None not in groups, burst
    assert ids[manifest["corrupt"][0]]["status"] == "error"


def test_hamming_and_phash_stable():
    im = Image.new("RGB", (64, 64), "white")
    h = imaging.phash(im)
    assert imaging.hamming(h, h) == 0
