"""Local storage for the Anthropic API key. The key never leaves the backend.

Order: ANTHROPIC_API_KEY environment variable, then the OS keychain (via `keyring`,
if installed), then a file in the app data directory readable only by the user.
"""
from __future__ import annotations

import os
from typing import Optional

from . import config

SERVICE = "WeddingAlbumCurator"
ACCOUNT = "anthropic_api_key"


def _file():
    return config.data_dir() / "secrets" / "anthropic_api_key"


def _keyring():
    try:
        import keyring

        keyring.get_keyring()
        return keyring
    except Exception:
        return None


def get_anthropic_key() -> Optional[str]:
    env = os.environ.get("ANTHROPIC_API_KEY")
    if env:
        return env.strip()
    kr = _keyring()
    if kr:
        try:
            v = kr.get_password(SERVICE, ACCOUNT)
            if v:
                return v
        except Exception:
            pass
    f = _file()
    if f.exists():
        return f.read_text().strip() or None
    return None


def key_source() -> Optional[str]:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "environment"
    kr = _keyring()
    if kr:
        try:
            if kr.get_password(SERVICE, ACCOUNT):
                return "keychain"
        except Exception:
            pass
    return "file" if _file().exists() else None


def set_anthropic_key(key: str) -> str:
    key = key.strip()
    if not key or len(key) > 500 or any(c.isspace() for c in key):
        raise ValueError("invalid API key format")
    kr = _keyring()
    if kr:
        try:
            kr.set_password(SERVICE, ACCOUNT, key)
            return "keychain"
        except Exception:
            pass
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(f.parent, 0o700)
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(key)
    return "file"


def delete_anthropic_key() -> None:
    kr = _keyring()
    if kr:
        try:
            kr.delete_password(SERVICE, ACCOUNT)
        except Exception:
            pass
    _file().unlink(missing_ok=True)
