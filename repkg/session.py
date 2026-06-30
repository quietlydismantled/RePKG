"""Save/load a capture session (before + after snapshots) to a single file.

Format: gzip-compressed JSON with version header. Extension: .repkg
"""
from __future__ import annotations

import gzip
import json

SESSION_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)
SESSION_EXT = ".repkg"


def save_session(before: dict, after: dict, path: str, meta: dict | None = None):
    payload = {
        "version": SESSION_VERSION,
        "meta": meta or {},
        "before": before,
        "after": after,
    }
    data = json.dumps(payload).encode("utf-8")
    with gzip.open(path, "wb") as f:
        f.write(data)


def load_session(path: str) -> tuple[dict, dict, dict]:
    """Returns (before, after, meta)."""
    with gzip.open(path, "rb") as f:
        payload = json.loads(f.read().decode("utf-8"))
    if payload.get("version") not in SUPPORTED_VERSIONS:
        raise ValueError(f"Unsupported session version: {payload.get('version')}")
    return payload["before"], payload["after"], payload.get("meta", {})
