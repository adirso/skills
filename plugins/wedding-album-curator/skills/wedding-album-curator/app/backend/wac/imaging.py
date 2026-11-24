"""Safe image decoding, metadata extraction, hashing and thumbnail generation.

All image files and their metadata are treated as untrusted input:
- Pillow's decompression-bomb guard is enforced (MAX_IMAGE_PIXELS).
- Files above MAX_FILE_BYTES are refused.
- EXIF values are parsed defensively; malformed values are ignored.
- Originals are only ever opened read-only.
"""
from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from . import config

Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS
warnings.simplefilter("error", Image.DecompressionBombWarning)

try:  # HEIC/HEIF support is optional at runtime
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except Exception:  # pragma: no cover - depends on platform wheels
    HEIF_SUPPORTED = False


class ImageError(Exception):
    """Raised when an image cannot be safely decoded."""


@dataclass
class DecodedImage:
    image: Image.Image  # RGB, EXIF-orientation corrected, at most WORK/PREVIEW size
    width: int  # oriented full-resolution size
    height: int
    format: str
    taken_at: Optional[str]
    taken_ts: Optional[float]
    camera: Optional[str]


EXIF_DATETIME_ORIGINAL = 0x9003
EXIF_DATETIME_DIGITIZED = 0x9004
EXIF_DATETIME = 0x0132
EXIF_SUBSEC_ORIGINAL = 0x9291
EXIF_MAKE = 0x010F
EXIF_MODEL = 0x0110
EXIF_IFD_POINTER = 0x8769


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _clean_str(value: object, limit: int = 64) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    s = "".join(ch for ch in str(value) if ch.isprintable()).strip().strip("\x00")
    return s[:limit] or None


def parse_exif_datetime(raw: object, subsec: object = None) -> Optional[datetime]:
    s = _clean_str(raw, 32)
    if not s:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            dt = datetime.strptime(s[:19], fmt)
            break
        except ValueError:
            continue
    else:
        return None
    if not (1990 <= dt.year <= 2100):  # obviously wrong camera clocks are ignored
        return None
    ss = _clean_str(subsec, 9)
    if ss and ss.isdigit():
        dt = dt.replace(microsecond=int(ss.ljust(6, "0")[:6]))
    return dt


def read_metadata(img: Image.Image) -> tuple[Optional[datetime], Optional[str]]:
    try:
        exif = img.getexif()
    except Exception:
        return None, None
    try:
        sub = exif.get_ifd(EXIF_IFD_POINTER)
    except Exception:
        sub = {}
    dt = None
    for tag in (EXIF_DATETIME_ORIGINAL, EXIF_DATETIME_DIGITIZED):
        dt = parse_exif_datetime(sub.get(tag), sub.get(EXIF_SUBSEC_ORIGINAL))
        if dt:
            break
    if dt is None:
        dt = parse_exif_datetime(exif.get(EXIF_DATETIME))
    make = _clean_str(exif.get(EXIF_MAKE))
    model = _clean_str(exif.get(EXIF_MODEL))
    camera = " ".join(x for x in (make, model) if x) or None
    return dt, camera


def open_image(path: Path, max_size: int = config.PREVIEW_SIZE) -> DecodedImage:
    """Decode an image safely, apply EXIF orientation, and downscale to max_size."""
    try:
        size = path.stat().st_size
    except OSError as e:
        raise ImageError(f"cannot stat file: {e}") from e
    if size > config.MAX_FILE_BYTES:
        raise ImageError("file too large")
    if size == 0:
        raise ImageError("empty file")
    try:
        with Image.open(path) as im:
            fmt = (im.format or "").upper()
            dt, camera = read_metadata(im)
            # draft() lets the JPEG decoder downscale during decode (much faster, less memory)
            if fmt == "JPEG":
                im.draft("RGB", (max_size, max_size))
            # Full-resolution oriented size from header info (before draft scaling)
            full_w, full_h = _oriented_full_size(im)
            im.load()
            oriented = ImageOps.exif_transpose(im)
            if oriented.mode not in ("RGB",):
                oriented = _to_rgb(oriented)
            oriented.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            out = oriented.copy()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        raise ImageError("image exceeds safe pixel limit") from e
    except UnidentifiedImageError as e:
        raise ImageError("unrecognized or unsupported image format") from e
    except (OSError, ValueError, SyntaxError, MemoryError) as e:
        raise ImageError(f"corrupt or unreadable image: {e}") from e
    return DecodedImage(
        image=out,
        width=full_w,
        height=full_h,
        format=fmt,
        taken_at=dt.isoformat() if dt else None,
        taken_ts=dt.timestamp() if dt else None,
        camera=camera,
    )


def _oriented_full_size(im: Image.Image) -> tuple[int, int]:
    w, h = im.size
    try:
        orientation = im.getexif().get(0x0112, 1)
    except Exception:
        orientation = 1
    if orientation in (5, 6, 7, 8):
        return h, w
    return w, h


def _to_rgb(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.asarray(im, dtype=np.float32)
        arr = (arr / max(float(arr.max()), 1.0) * 255).clip(0, 255).astype(np.uint8)
        return Image.fromarray(arr).convert("RGB")
    return im.convert("RGB")


def save_jpeg(img: Image.Image, dest: Path, max_size: int, quality: int = 85) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = img
    if max(im.size) > max_size:
        im = im.copy()
        im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    tmp = dest.with_suffix(".tmp")
    im.save(tmp, "JPEG", quality=quality, optimize=True, progressive=True)
    tmp.replace(dest)


def jpeg_bytes(img: Image.Image, max_size: int, quality: int = 85) -> bytes:
    im = img.copy()
    im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def phash(img: Image.Image) -> str:
    """64-bit DCT perceptual hash as 16 hex chars."""
    import cv2

    g = np.asarray(img.convert("L").resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float32)
    d = cv2.dct(g)[:8, :8]
    med = np.median(d[1:, 1:]) if d.size > 1 else 0
    bits = (d > med).flatten()
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return f"{value:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def to_bgr(img: Image.Image) -> np.ndarray:
    arr = np.asarray(img.convert("RGB"))
    return arr[:, :, ::-1].copy()


def resize_long(img: Image.Image, size: int) -> Image.Image:
    if max(img.size) <= size:
        return img
    im = img.copy()
    im.thumbnail((size, size), Image.Resampling.LANCZOS)
    return im
