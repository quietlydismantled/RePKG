"""Filesystem scan engines: full walk (any FS) and USN journal (NTFS, fast).

Both expose:
  capture(phase, roots, excl, progress_cb=None, before_state=None) -> state dict
  file_changes(before_state, after_state, roots, excl) -> (added, modified, deleted)

The (added, modified, deleted) triples match the shapes produced by
`differ.diff_files`, so the UI/exporter handle both engines identically.
"""
from __future__ import annotations

import os
from typing import Optional

from . import usn
from .differ import diff_files
from .snapshotter import _md5, snapshot_filesystem


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(p))


def _is_self_artifact(path: str) -> bool:
    name = os.path.basename(path)
    return name.startswith("repkg_") and name.lower().endswith((".json", ".repkg"))


def _in_scope(path: str, roots, exclusions) -> bool:
    np = _norm(path)
    under_root = False
    for r in roots:
        nr = _norm(r)
        if np == nr or np.startswith(nr + os.sep):
            under_root = True
            break
    if not under_root:
        return False
    for ex in exclusions:
        ne = _norm(ex)
        if np == ne or np.startswith(ne + os.sep):
            return False
    if _is_self_artifact(path):
        return False
    return True


def _file_meta(path: str) -> Optional[dict]:
    try:
        st = os.stat(path)
    except (OSError, PermissionError):
        return None
    return {"size": st.st_size, "mtime": st.st_mtime, "md5": _md5(path)}


class WalkEngine:
    name = "snapshot"

    def capture(self, phase, roots, exclusions, progress_cb=None, before_state=None) -> dict:
        return {"filesystem": snapshot_filesystem(roots, exclusions, progress_cb)}

    def file_changes(self, before, after, roots, exclusions):
        return diff_files(before.get("filesystem", {}), after.get("filesystem", {}))


class UsnEngine:
    name = "usn"

    def capture(self, phase, roots, exclusions, progress_cb=None, before_state=None) -> dict:
        vols = usn.volumes_for_roots(roots)
        if phase == "before":
            return {"usn_checkpoints": usn.checkpoint(vols)}
        # after: read the journal since the before-checkpoints (worker thread)
        if progress_cb:
            progress_cb("Reading USN journal…")
        cps = (before_state or {}).get("usn_checkpoints", {})
        records = usn.read_changes(vols, cps)
        # store as {path: reason_int} (already that shape)
        return {"usn_records": records}

    def file_changes(self, before, after, roots, exclusions):
        records = after.get("usn_records", {})
        added, modified, deleted = {}, {}, {}
        for path, reasons in records.items():
            if not _in_scope(path, roots, exclusions):
                continue
            kind = usn.classify(path, reasons)
            if kind == "added":
                meta = _file_meta(path)
                if meta:
                    added[path] = meta
            elif kind == "modified":
                meta = _file_meta(path)
                if meta:
                    modified[path] = {"before": {}, "after": meta}
            elif kind == "deleted":
                deleted[path] = {"size": 0, "mtime": 0, "md5": None}
        return added, modified, deleted


def make_engine(name: str):
    return UsnEngine() if name == "usn" else WalkEngine()
