"""Application-wide configuration and filesystem locations."""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "WeddingAlbumCurator"
VERSION = "0.1.0"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# Image safety limits. Pillow raises DecompressionBombError above 2x this value.
MAX_IMAGE_PIXELS = 200_000_000  # ~200 MP; larger than any current camera sensor
MAX_FILE_BYTES = 400 * 1024 * 1024  # skip files larger than 400 MB

THUMB_SIZE = 400  # long edge, grid thumbnails
PREVIEW_SIZE = 2048  # long edge, viewer previews
WORK_SIZE = 1600  # long edge, analysis working copy

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff",
}


def data_dir() -> Path:
    """Root of all local application data (projects, caches, models)."""
    override = os.environ.get("WAC_DATA_DIR")
    path = Path(override).expanduser() if override else Path(user_data_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    p = data_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def projects_dir() -> Path:
    p = data_dir() / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def frontend_dist() -> Path:
    override = os.environ.get("WAC_FRONTEND_DIST")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"
