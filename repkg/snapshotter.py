import hashlib
import json
import os
import winreg
from pathlib import Path
from typing import Callable, Optional

DEFAULT_FS_ROOTS = [
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData",
    str(Path.home() / "AppData"),
]

DEFAULT_FS_EXCLUSIONS = [
    r"C:\Program Files\WindowsApps",
    r"C:\ProgramData\Microsoft\Windows\WER",
]

DEFAULT_REG_HIVES = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE"),
    (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services"),
]

HIVE_NAMES = {
    winreg.HKEY_LOCAL_MACHINE: "HKEY_LOCAL_MACHINE",
    winreg.HKEY_CURRENT_USER: "HKEY_CURRENT_USER",
    winreg.HKEY_CLASSES_ROOT: "HKEY_CLASSES_ROOT",
    winreg.HKEY_USERS: "HKEY_USERS",
}


def _md5(path: str) -> Optional[str]:
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, OSError):
        return None


def snapshot_filesystem(
    roots: list[str],
    exclusions: list[str],
    progress_cb: Optional[Callable[[str], None]] = None,
) -> dict:
    snapshot = {}
    excl_lower = [e.lower() for e in exclusions]

    for root in roots:
        root = os.path.normpath(root)
        if not os.path.exists(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dp_lower = dirpath.lower()
            if any(dp_lower.startswith(e) for e in excl_lower):
                dirnames.clear()
                continue
            for fname in filenames:
                # Self-exclusion: skip RePKG's own temp snapshot/session artifacts
                if fname.startswith("repkg_") and fname.endswith((".json", ".repkg")):
                    continue
                fpath = os.path.join(dirpath, fname)
                if progress_cb:
                    progress_cb(fpath)
                try:
                    st = os.stat(fpath)
                    snapshot[fpath] = {
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "md5": _md5(fpath),
                    }
                except (PermissionError, OSError):
                    pass
    return snapshot


def _walk_registry_key(hive_handle, hive_name: str, key_path: str, snapshot: dict):
    try:
        key = winreg.OpenKey(hive_handle, key_path, 0, winreg.KEY_READ)
    except (PermissionError, OSError, FileNotFoundError):
        return

    try:
        i = 0
        while True:
            try:
                name, data, reg_type = winreg.EnumValue(key, i)
                full_key = f"{hive_name}\\{key_path}"
                value_key = f"{full_key}\\{name}" if name else f"{full_key}\\"
                snapshot[value_key] = {
                    "type": reg_type,
                    "data": repr(data),
                    "key": full_key,
                    "value_name": name,
                }
                i += 1
            except OSError:
                break

        j = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, j)
                sub_path = f"{key_path}\\{subkey_name}"
                _walk_registry_key(hive_handle, hive_name, sub_path, snapshot)
                j += 1
            except OSError:
                break
    finally:
        winreg.CloseKey(key)


def snapshot_registry(
    hives: list[tuple],
    progress_cb: Optional[Callable[[str], None]] = None,
) -> dict:
    snapshot = {}
    for hive_handle, key_path in hives:
        hive_name = HIVE_NAMES.get(hive_handle, str(hive_handle))
        if progress_cb:
            progress_cb(f"{hive_name}\\{key_path}")
        _walk_registry_key(hive_handle, hive_name, key_path, snapshot)
    return snapshot


def save_snapshot(snapshot: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f)


def load_snapshot(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
