"""Generate a small synthetic sample "wedding" folder for demos and tests.

The images are procedurally generated scenes (no real wedding photos). If face fixture
images are supplied, cropped/adjusted variations of them are added so that face
detection and people grouping have something real to work with.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

EXIF_IFD = 0x8769
DATETIME_ORIGINAL = 0x9003
ORIENTATION = 0x0112


def _scene(rng: random.Random, w: int = 1200, h: int = 800) -> Image.Image:
    base = np.zeros((h, w, 3), np.float32)
    c1 = np.array([rng.randint(30, 220) for _ in range(3)], np.float32)
    c2 = np.array([rng.randint(30, 220) for _ in range(3)], np.float32)
    t = np.linspace(0, 1, h)[:, None, None]
    base[:] = c1 * (1 - t) + c2 * t
    img = Image.fromarray(base.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    for _ in range(rng.randint(6, 14)):
        x, y = rng.randint(0, w), rng.randint(0, h)
        r = rng.randint(20, 160)
        col = tuple(rng.randint(0, 255) for _ in range(3))
        if rng.random() < 0.5:
            d.ellipse((x - r, y - r, x + r, y + r), fill=col)
        else:
            d.rectangle((x - r, y - r // 2, x + r, y + r // 2), fill=col)
    # fine texture so sharpness is measurable
    noise = np.random.default_rng(rng.randint(0, 10**6)).normal(0, 6, (h, w, 3))
    arr = np.asarray(img, np.float32) + noise
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def _save(img: Image.Image, path: Path, when: Optional[datetime], orientation: int = 1, fmt: Optional[str] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    if orientation != 1:
        exif[ORIENTATION] = orientation
    if when:
        exif.get_ifd(EXIF_IFD)[DATETIME_ORIGINAL] = when.strftime("%Y:%m:%d %H:%M:%S")
    fmt = fmt or {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP", ".tif": "TIFF", ".heic": "HEIF"}[path.suffix.lower()]
    kwargs = {"exif": exif} if fmt in ("JPEG", "WEBP", "PNG", "TIFF", "HEIF") else {}
    if fmt == "JPEG":
        kwargs["quality"] = 90
    img.save(path, fmt, **kwargs)


def generate(dest: Path, n_scenes: int = 30, faces_dir: Optional[Path] = None, seed: int = 7) -> dict:
    """Create the sample folder. Returns a manifest of what was generated (for tests)."""
    rng = random.Random(seed)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    start = datetime(2025, 6, 12, 10, 0, 0)
    manifest: dict = {"files": [], "bursts": [], "exact_duplicates": [], "blurry": [], "dark": [], "faces": [],
                      "rotated": [], "corrupt": [], "formats": {}}
    t = start
    sub_dirs = ["01_getting_ready", "02_ceremony", "03_portraits", "04_reception"]
    for i in range(n_scenes):
        sub = sub_dirs[min(len(sub_dirs) - 1, i * len(sub_dirs) // n_scenes)]
        t += timedelta(minutes=rng.randint(3, 25))
        img = _scene(rng)
        name = dest / sub / f"IMG_{1000 + i:04d}.jpg"
        _save(img, name, t)
        manifest["files"].append(str(name.relative_to(dest)))
        if i % 6 == 0:  # burst of near-duplicates
            burst = [str(name.relative_to(dest))]
            for k in range(1, 3):
                shifted = img.transform(img.size, Image.Transform.AFFINE, (1, 0, k * 4, 0, 1, k * 2))
                shifted = ImageEnhance.Brightness(shifted).enhance(1 + 0.03 * k)
                bn = dest / sub / f"IMG_{1000 + i:04d}_b{k}.jpg"
                _save(shifted, bn, t + timedelta(seconds=k))
                burst.append(str(bn.relative_to(dest)))
            manifest["bursts"].append(burst)
        if i % 7 == 3:  # blurry version
            bl = dest / sub / f"IMG_{1000 + i:04d}_blur.jpg"
            _save(img.filter(ImageFilter.GaussianBlur(8)), bl, t + timedelta(seconds=5))
            manifest["blurry"].append(str(bl.relative_to(dest)))
        if i % 9 == 4:  # underexposed
            dk = dest / sub / f"IMG_{1000 + i:04d}_dark.jpg"
            _save(ImageEnhance.Brightness(img).enhance(0.12), dk, t + timedelta(seconds=40))
            manifest["dark"].append(str(dk.relative_to(dest)))
    # exact duplicate (copied file in another folder)
    first = dest / manifest["files"][0]
    dup = dest / "backup" / first.name
    dup.parent.mkdir(exist_ok=True)
    dup.write_bytes(first.read_bytes())
    manifest["exact_duplicates"].append([manifest["files"][0], str(dup.relative_to(dest))])
    # EXIF-rotated photo (stored landscape, displayed portrait)
    rot = dest / "03_portraits" / "IMG_ROT.jpg"
    _save(_scene(rng, 900, 600), rot, t + timedelta(minutes=1), orientation=6)
    manifest["rotated"].append(str(rot.relative_to(dest)))
    # other formats
    for ext, fmt in ((".png", "PNG"), (".webp", "WEBP"), (".tif", "TIFF")):
        p = dest / "04_reception" / f"FORMAT_TEST{ext}"
        _save(_scene(rng, 800, 600), p, t + timedelta(minutes=2), fmt=fmt)
        manifest["formats"][ext] = str(p.relative_to(dest))
    try:
        import pillow_heif  # noqa: F401

        p = dest / "04_reception" / "FORMAT_TEST.heic"
        _save(_scene(rng, 800, 600), p, t + timedelta(minutes=3), fmt="HEIF")
        manifest["formats"][".heic"] = str(p.relative_to(dest))
    except Exception:
        pass
    # corrupt file and an unsupported file (must be skipped / reported, never crash)
    bad = dest / "04_reception" / "CORRUPT.jpg"
    bad.write_bytes(b"\xff\xd8\xff\xe0" + bytes(rng.getrandbits(8) for _ in range(2000)))
    manifest["corrupt"].append(str(bad.relative_to(dest)))
    (dest / "notes.txt").write_text("not an image")
    # faces from fixtures
    if faces_dir and Path(faces_dir).is_dir():
        ft = start + timedelta(hours=3)
        for j, f in enumerate(sorted(Path(faces_dir).glob("*.jpg"))):
            with Image.open(f) as im:
                im = im.convert("RGB")
                for k, enh in enumerate((1.0, 0.85, 1.15)):
                    var = ImageEnhance.Brightness(im).enhance(enh)
                    if k == 2:
                        var = var.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    p = dest / "03_portraits" / f"FACE_{j}_{k}.jpg"
                    _save(var, p, ft + timedelta(minutes=10 * j, seconds=30 * k))
                    manifest["faces"].append(str(p.relative_to(dest)))
    return manifest
