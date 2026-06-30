"""NTFS USN change-journal reader (pure ctypes, no pywin32).

Provides a fast filesystem-diff path: record a per-volume USN checkpoint
before an installer runs, then read the journal afterward to get exactly the
files that changed — O(changes) instead of walking every file.

Windows/NTFS + admin only. Callers must guard with is_available() and fall
back to the walk engine when it returns False.
"""
from __future__ import annotations

import ctypes
import os
import struct
from ctypes import wintypes
from typing import Optional

_IS_WINDOWS = os.name == "nt"

# ---- constants ----
FSCTL_QUERY_USN_JOURNAL = 0x000900F4
FSCTL_READ_USN_JOURNAL = 0x000900BB

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# USN reason flags
R_DATA_OVERWRITE = 0x00000001
R_DATA_EXTEND = 0x00000002
R_DATA_TRUNCATION = 0x00000004
R_NAMED_DATA_OVERWRITE = 0x00000010
R_NAMED_DATA_EXTEND = 0x00000020
R_NAMED_DATA_TRUNCATION = 0x00000040
R_FILE_CREATE = 0x00000100
R_FILE_DELETE = 0x00000200
R_RENAME_OLD_NAME = 0x00001000
R_RENAME_NEW_NAME = 0x00002000

R_DATA_ANY = (
    R_DATA_OVERWRITE | R_DATA_EXTEND | R_DATA_TRUNCATION
    | R_NAMED_DATA_OVERWRITE | R_NAMED_DATA_EXTEND | R_NAMED_DATA_TRUNCATION
)


class UsnError(Exception):
    pass


class UsnWrapError(UsnError):
    """Journal wrapped or was reset since the checkpoint — fall back to walk."""


# ---- structures ----
class USN_JOURNAL_DATA_V0(ctypes.Structure):
    _fields_ = [
        ("UsnJournalID", ctypes.c_ulonglong),
        ("FirstUsn", ctypes.c_longlong),
        ("NextUsn", ctypes.c_longlong),
        ("LowestValidUsn", ctypes.c_longlong),
        ("MaxUsn", ctypes.c_longlong),
        ("MaximumSize", ctypes.c_ulonglong),
        ("AllocationDelta", ctypes.c_ulonglong),
    ]


class READ_USN_JOURNAL_DATA_V0(ctypes.Structure):
    _fields_ = [
        ("StartUsn", ctypes.c_longlong),
        ("ReasonMask", ctypes.c_ulong),
        ("ReturnOnlyOnClose", ctypes.c_ulong),
        ("Timeout", ctypes.c_ulonglong),
        ("BytesToWaitFor", ctypes.c_ulonglong),
        ("UsnJournalID", ctypes.c_ulonglong),
    ]


class USN_RECORD_V2(ctypes.Structure):
    _fields_ = [
        ("RecordLength", ctypes.c_ulong),
        ("MajorVersion", ctypes.c_ushort),
        ("MinorVersion", ctypes.c_ushort),
        ("FileReferenceNumber", ctypes.c_ulonglong),
        ("ParentFileReferenceNumber", ctypes.c_ulonglong),
        ("Usn", ctypes.c_longlong),
        ("TimeStamp", ctypes.c_longlong),
        ("Reason", ctypes.c_ulong),
        ("SourceInfo", ctypes.c_ulong),
        ("SecurityId", ctypes.c_ulong),
        ("FileAttributes", ctypes.c_ulong),
        ("FileNameLength", ctypes.c_ushort),
        ("FileNameOffset", ctypes.c_ushort),
        # FileName WCHAR[1] follows — read manually from the buffer
    ]


class FILE_ID_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),       # 0 = FileIdType
        ("FileId", ctypes.c_byte * 16), # union (GUID-sized); first 8 bytes = file id
    ]


if _IS_WINDOWS:
    _k32 = ctypes.windll.kernel32

    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _k32.DeviceIoControl.restype = wintypes.BOOL
    _k32.DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.OpenFileById.restype = wintypes.HANDLE
    _k32.OpenFileById.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(FILE_ID_DESCRIPTOR), wintypes.DWORD,
        wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
    ]
    _k32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    _k32.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
    ]
    _k32.GetVolumeInformationW.restype = wintypes.BOOL


# ---- helpers ----
def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def volume_of(path: str) -> str:
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    return drive.upper()  # e.g. "C:"


def volumes_for_roots(roots) -> list:
    seen = []
    for r in roots:
        v = volume_of(r)
        if v and v not in seen:
            seen.append(v)
    return seen


def is_ntfs(volume: str) -> bool:
    if not _IS_WINDOWS:
        return False
    fsname = ctypes.create_unicode_buffer(64)
    ok = _k32.GetVolumeInformationW(
        ctypes.c_wchar_p(volume + "\\"), None, 0, None, None, None, fsname, 64
    )
    return bool(ok) and fsname.value.upper() == "NTFS"


def _open_volume(volume: str):
    handle = _k32.CreateFileW(
        r"\\.\%s" % volume,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None,
    )
    if not handle or handle == INVALID_HANDLE_VALUE:
        raise UsnError(f"Cannot open volume {volume} (err {ctypes.get_last_error()})")
    return handle


def _query_journal(handle) -> USN_JOURNAL_DATA_V0:
    out = USN_JOURNAL_DATA_V0()
    returned = wintypes.DWORD(0)
    ok = _k32.DeviceIoControl(
        handle, FSCTL_QUERY_USN_JOURNAL, None, 0,
        ctypes.byref(out), ctypes.sizeof(out), ctypes.byref(returned), None,
    )
    if not ok:
        raise UsnError(f"USN journal not active (err {ctypes.get_last_error()})")
    return out


def is_available(roots) -> tuple:
    """Returns (ok, reason)."""
    if not _IS_WINDOWS:
        return False, "USN journal is Windows-only"
    if not _is_admin():
        return False, "USN journal requires running as Administrator"
    vols = volumes_for_roots(roots)
    if not vols:
        return False, "No volumes resolved from scan roots"
    for v in vols:
        if not is_ntfs(v):
            return False, f"Volume {v} is not NTFS"
        try:
            h = _open_volume(v)
        except UsnError as e:
            return False, str(e)
        try:
            _query_journal(h)
        except UsnError as e:
            return False, str(e)
        finally:
            _k32.CloseHandle(h)
    return True, ""


def checkpoint(volumes) -> dict:
    """Record current journal id + next-USN per volume. Near-instant."""
    cps = {}
    for v in volumes:
        h = _open_volume(v)
        try:
            j = _query_journal(h)
            cps[v] = {"journal_id": j.UsnJournalID, "next_usn": j.NextUsn}
        finally:
            _k32.CloseHandle(h)
    return cps


def _path_from_frn(vol_handle, frn: int) -> Optional[str]:
    fid = FILE_ID_DESCRIPTOR()
    fid.dwSize = ctypes.sizeof(FILE_ID_DESCRIPTOR)
    fid.Type = 0
    raw = struct.pack("<Q", frn & 0xFFFFFFFFFFFFFFFF)
    for i, b in enumerate(raw):
        fid.FileId[i] = b if b < 128 else b - 256
    h = _k32.OpenFileById(
        vol_handle, ctypes.byref(fid), 0,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, None,
        FILE_FLAG_BACKUP_SEMANTICS,
    )
    if not h or h == INVALID_HANDLE_VALUE:
        return None
    try:
        buf = ctypes.create_unicode_buffer(32768)
        n = _k32.GetFinalPathNameByHandleW(h, buf, 32768, 0)
        if n == 0 or n >= 32768:
            return None
        return _strip_prefix(buf.value)
    finally:
        _k32.CloseHandle(h)


def _strip_prefix(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def read_changes(volumes, checkpoints: dict) -> dict:
    """Read journal since each checkpoint. Returns {abs_path: set(reason_ints)}.

    Raises UsnWrapError if a journal was reset/wrapped past the checkpoint.
    """
    result: dict = {}
    for v in volumes:
        cp = checkpoints.get(v)
        if not cp:
            continue
        h = _open_volume(v)
        try:
            j = _query_journal(h)
            if j.UsnJournalID != cp["journal_id"] or cp["next_usn"] < j.LowestValidUsn:
                raise UsnWrapError(f"Journal on {v} wrapped since checkpoint")
            _read_volume(h, v, cp, result)
        finally:
            _k32.CloseHandle(h)
    return result


def _read_volume(h, volume: str, cp: dict, result: dict):
    # frn -> {"parent", "name", "reasons"}; plus old-name deletions
    by_frn: dict = {}
    old_names: list = []

    read = READ_USN_JOURNAL_DATA_V0()
    read.StartUsn = cp["next_usn"]
    read.ReasonMask = 0xFFFFFFFF
    read.ReturnOnlyOnClose = 0
    read.Timeout = 0
    read.BytesToWaitFor = 0
    read.UsnJournalID = cp["journal_id"]

    buf = ctypes.create_string_buffer(65536)
    returned = wintypes.DWORD(0)

    while True:
        ok = _k32.DeviceIoControl(
            h, FSCTL_READ_USN_JOURNAL, ctypes.byref(read), ctypes.sizeof(read),
            buf, ctypes.sizeof(buf), ctypes.byref(returned), None,
        )
        if not ok:
            break
        n = returned.value
        if n <= 8:
            break
        next_usn = struct.unpack_from("<q", buf.raw, 0)[0]
        offset = 8
        while offset < n:
            rec = USN_RECORD_V2.from_buffer_copy(buf.raw, offset)
            if rec.RecordLength == 0:
                break
            name = buf.raw[
                offset + rec.FileNameOffset:
                offset + rec.FileNameOffset + rec.FileNameLength
            ].decode("utf-16-le", "replace")
            if rec.Reason & R_RENAME_OLD_NAME:
                old_names.append((rec.ParentFileReferenceNumber, name, rec.Reason))
            entry = by_frn.get(rec.FileReferenceNumber)
            if entry is None:
                by_frn[rec.FileReferenceNumber] = {
                    "parent": rec.ParentFileReferenceNumber,
                    "name": name,
                    "reasons": rec.Reason,
                }
            else:
                entry["reasons"] |= rec.Reason
                if not (rec.Reason & R_RENAME_OLD_NAME):
                    entry["parent"] = rec.ParentFileReferenceNumber
                    entry["name"] = name
            offset += rec.RecordLength
        read.StartUsn = next_usn

    dir_cache: dict = {}

    def resolve(parent_frn: int, name: str) -> Optional[str]:
        pdir = dir_cache.get(parent_frn)
        if pdir is None:
            pdir = _path_from_frn(h, parent_frn)
            dir_cache[parent_frn] = pdir
        if pdir:
            return os.path.join(pdir, name)
        return None

    for frn, info in by_frn.items():
        path = resolve(info["parent"], info["name"])
        if not path:
            path = _path_from_frn(h, frn)
        if not path:
            continue
        result.setdefault(path, 0)
        result[path] |= info["reasons"]

    for parent_frn, name, reason in old_names:
        path = resolve(parent_frn, name)
        if path:
            result.setdefault(path, 0)
            result[path] |= reason

    # normalize int masks to sets is unnecessary; keep ints
    return result


def classify(path: str, reasons: int) -> Optional[str]:
    """Map a coalesced reason mask + current existence to a change type."""
    has_create = bool(reasons & R_FILE_CREATE)
    has_delete = bool(reasons & R_FILE_DELETE)
    has_data = bool(reasons & R_DATA_ANY)
    has_rename_new = bool(reasons & R_RENAME_NEW_NAME)
    exists = os.path.exists(path)

    if has_create and has_delete and not exists:
        return None  # created and removed within the window (temp file)
    if has_delete and not exists:
        return "deleted"
    if has_create and not exists:
        return None  # created then removed within the window (temp)
    if has_create and exists:
        return "added"
    if exists and has_rename_new:
        return "added"   # moved into a watched location
    if exists and has_data:
        return "modified"
    return None  # metadata-only touch, or unresolved
