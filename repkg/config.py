"""Persistent app config — stored as JSON in %APPDATA%\\RePKG\\config.json."""
from __future__ import annotations

import json
import os

APP_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "RePKG"
)
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    "fs_roots": None,        # None -> use built-in defaults; else [{"path","checked"}]
    "exclusions": None,      # None -> built-in defaults; else [str]
    "reg_hives": None,       # None -> built-in; else {label: checked}
    "settle_delay": 5,
    "theme": "dark",
    "last_output_dir": "",          # legacy (v<=current); migrated into history
    "output_dir_history": [],       # recent export dirs, most-recent first
    "scan_engine": "snapshot",      # "snapshot" (walk) | "usn"
}


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {**DEFAULTS, **data}
    except (OSError, ValueError):
        pass
    return dict(DEFAULTS)


def save_config(cfg: dict):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass
