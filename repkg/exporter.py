import json
import os
import re
import shutil
import winreg
from pathlib import Path
from typing import Callable, Optional

from .differ import ChangeSet

REG_TYPE_NAMES = {
    winreg.REG_SZ: "REG_SZ",
    winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ",
    winreg.REG_BINARY: "REG_BINARY",
    winreg.REG_DWORD: "REG_DWORD",
    winreg.REG_DWORD_BIG_ENDIAN: "REG_DWORD_BIG_ENDIAN",
    winreg.REG_LINK: "REG_LINK",
    winreg.REG_MULTI_SZ: "REG_MULTI_SZ",
    winreg.REG_QWORD: "REG_QWORD",
}


def _safe_path(file_path: str, output_dir: str) -> str:
    # Normalize slashes first, then strip drive colon: C:\foo -> FILES\C\foo
    p = os.path.normpath(file_path)
    if len(p) >= 2 and p[1] == ":":
        p = p[0] + p[2:]  # "C:\foo" -> "C\foo"
    p = p.lstrip("\\")
    return os.path.join(output_dir, "FILES", p)


def _format_reg_value(value_name: str, data_repr: str, reg_type: int) -> str:
    # Reconstruct the actual data from repr string for .reg formatting
    try:
        data = eval(data_repr)  # safe — we wrote it ourselves via repr()
    except Exception:
        data = data_repr

    quoted_name = f'"{value_name}"' if value_name else "@"

    if reg_type == winreg.REG_SZ:
        escaped = str(data).replace("\\", "\\\\").replace('"', '\\"')
        return f'{quoted_name}="{escaped}"'
    elif reg_type == winreg.REG_EXPAND_SZ:
        hex_bytes = str(data).encode("utf-16-le").hex()
        hex_pairs = ",".join(hex_bytes[i:i+2] for i in range(0, len(hex_bytes), 2))
        return f"{quoted_name}=hex(2):{hex_pairs}"
    elif reg_type == winreg.REG_DWORD:
        return f"{quoted_name}=dword:{int(data):08x}"
    elif reg_type == winreg.REG_QWORD:
        val = int(data)
        hex_bytes = val.to_bytes(8, "little").hex()
        hex_pairs = ",".join(hex_bytes[i:i+2] for i in range(0, len(hex_bytes), 2))
        return f"{quoted_name}=hex(b):{hex_pairs}"
    elif reg_type == winreg.REG_BINARY:
        if isinstance(data, bytes):
            hex_pairs = ",".join(f"{b:02x}" for b in data)
        else:
            hex_pairs = ""
        return f"{quoted_name}=hex:{hex_pairs}"
    elif reg_type == winreg.REG_MULTI_SZ:
        combined = "\x00".join(data) + "\x00\x00" if isinstance(data, list) else ""
        hex_bytes = combined.encode("utf-16-le").hex()
        hex_pairs = ",".join(hex_bytes[i:i+2] for i in range(0, len(hex_bytes), 2))
        return f"{quoted_name}=hex(7):{hex_pairs}"
    else:
        # Fallback: hex
        if isinstance(data, bytes):
            hex_pairs = ",".join(f"{b:02x}" for b in data)
        else:
            hex_pairs = ""
        type_hex = f"{reg_type:x}"
        return f"{quoted_name}=hex({type_hex}):{hex_pairs}"


def export(
    changeset: ChangeSet,
    selected_files: set,
    selected_reg_keys: set,
    output_dir: str,
    progress_cb: Optional[Callable[[str], None]] = None,
):
    os.makedirs(output_dir, exist_ok=True)
    manifest = {"files": {}, "registry": {}}

    # Export files
    for path in selected_files:
        if path in changeset.files_added:
            meta = changeset.files_added[path]
            change_type = "added"
        elif path in changeset.files_modified:
            meta = changeset.files_modified[path]["after"]
            change_type = "modified"
        else:
            continue

        dest = _safe_path(path, output_dir)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if progress_cb:
            progress_cb(f"Copying: {path}")
        try:
            shutil.copy2(path, dest)
            manifest["files"][path] = {
                "change": change_type,
                "dest": dest,
                **meta,
            }
        except (PermissionError, OSError) as e:
            manifest["files"][path] = {"change": change_type, "error": str(e)}

    # Build .reg file grouped by key path
    reg_lines = ["Windows Registry Editor Version 5.00", ""]
    keys_grouped: dict[str, list] = {}

    for value_key in selected_reg_keys:
        if value_key in changeset.reg_added:
            entry = changeset.reg_added[value_key]
            change_type = "added"
        elif value_key in changeset.reg_modified:
            entry = changeset.reg_modified[value_key]["after"]
            change_type = "modified"
        else:
            continue

        key_path = entry.get("key", "")
        if key_path not in keys_grouped:
            keys_grouped[key_path] = []
        keys_grouped[key_path].append((entry, change_type, value_key))

    for key_path, entries in keys_grouped.items():
        reg_lines.append(f"[{key_path}]")
        for entry, change_type, value_key in entries:
            value_name = entry.get("value_name", "")
            data_repr = entry.get("data", "")
            reg_type = entry.get("type", winreg.REG_SZ)
            line = _format_reg_value(value_name, data_repr, reg_type)
            reg_lines.append(line)
            manifest["registry"][value_key] = {"change": change_type, **entry}
        reg_lines.append("")

    reg_path = os.path.join(output_dir, "registry_changes.reg")
    with open(reg_path, "w", encoding="utf-16") as f:
        f.write("\n".join(reg_lines))

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # WiX source for real MSI repackaging
    if progress_cb:
        progress_cb("Generating WiX source (setup.wxs)…")
    try:
        wxs = generate_wxs(manifest, output_dir)
        with open(os.path.join(output_dir, "setup.wxs"), "w", encoding="utf-8") as f:
            f.write(wxs)
    except Exception as e:
        if progress_cb:
            progress_cb(f"WiX generation skipped: {e}")

    if progress_cb:
        progress_cb("Done.")

    return manifest


# ----------------------------------------------------------------------------
# WiX (.wxs) generation — WiX Toolset v3 schema
# ----------------------------------------------------------------------------

_REG_ROOT = {
    "HKEY_LOCAL_MACHINE": "HKLM",
    "HKEY_CURRENT_USER": "HKCU",
    "HKEY_CLASSES_ROOT": "HKCR",
    "HKEY_USERS": "HKU",
}


def _wid(prefix: str, s: str) -> str:
    import hashlib
    return f"{prefix}_{hashlib.md5(s.encode('utf-8', 'replace')).hexdigest()[:16]}"


def _xml_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _wix_reg_type(reg_type: int, data):
    if reg_type in (winreg.REG_SZ,):
        return "string", str(data)
    if reg_type == winreg.REG_EXPAND_SZ:
        return "expandable", str(data)
    if reg_type in (winreg.REG_DWORD, winreg.REG_QWORD):
        try:
            return "integer", str(int(data))
        except (ValueError, TypeError):
            return "string", str(data)
    if reg_type == winreg.REG_BINARY:
        if isinstance(data, bytes):
            return "binary", data.hex()
        return "binary", ""
    if reg_type == winreg.REG_MULTI_SZ:
        if isinstance(data, list):
            return "multiString", "[~]".join(data)
        return "multiString", str(data)
    return "string", str(data)


def generate_wxs(manifest: dict, output_dir: str, product_name: str = "Repackaged Application") -> str:
    # --- Build directory tree from file paths ---
    dirs: dict[str, dict] = {}  # norm_path -> {id, name, parent}

    def ensure_dir(path: str) -> str:
        path = os.path.normpath(path)
        if path in dirs:
            return dirs[path]["id"]
        drive, rest = os.path.splitdrive(path)
        if rest in ("", "\\", "/"):  # drive root, e.g. "C:\"
            name = (drive.rstrip(":") or "ROOT")
            dirs[path] = {"id": _wid("dir", path), "name": name, "parent": "TARGETDIR"}
            return dirs[path]["id"]
        parent = os.path.dirname(path)
        parent_id = ensure_dir(parent)
        dirs[path] = {"id": _wid("dir", path), "name": os.path.basename(path), "parent": parent_id}
        return dirs[path]["id"]

    file_components = []  # (component_id, dir_id, file_id, source_rel, name)
    for path, meta in manifest.get("files", {}).items():
        if "dest" not in meta:  # failed copy
            continue
        dir_id = ensure_dir(os.path.dirname(path))
        source_rel = os.path.relpath(meta["dest"], output_dir)
        file_components.append((
            _wid("cmp", path),
            dir_id,
            _wid("fil", path),
            source_rel,
            os.path.basename(path),
        ))

    # --- Registry components ---
    reg_components = []
    for value_key, entry in manifest.get("registry", {}).items():
        key_full = entry.get("key", "")
        parts = key_full.split("\\", 1)
        hive = parts[0]
        sub = parts[1] if len(parts) > 1 else ""
        root = _REG_ROOT.get(hive)
        if root is None:
            continue
        try:
            data = eval(entry.get("data", "''"))
        except Exception:
            data = entry.get("data", "")
        wtype, wval = _wix_reg_type(entry.get("type", winreg.REG_SZ), data)
        reg_components.append({
            "cid": _wid("reg", value_key),
            "root": root,
            "key": sub,
            "name": entry.get("value_name", ""),
            "type": wtype,
            "value": wval,
        })

    # --- Emit XML ---
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">')
    lines.append(f'  <Product Id="*" Name="{_xml_escape(product_name)}" Language="1033" '
                 f'Version="1.0.0.0" Manufacturer="RePKG" '
                 f'UpgradeCode="{{PUT-A-STABLE-GUID-HERE}}">')
    lines.append('    <Package InstallerVersion="500" Compressed="yes" InstallScope="perMachine" />')
    lines.append('    <MediaTemplate EmbedCab="yes" />')
    lines.append('')
    lines.append('    <Directory Id="TARGETDIR" Name="SourceDir">')

    # Build children map for nesting
    children: dict[str, list[str]] = {}
    for path, info in dirs.items():
        children.setdefault(info["parent"], []).append(path)

    files_by_dir: dict[str, list] = {}
    for comp in file_components:
        files_by_dir.setdefault(comp[1], []).append(comp)

    def emit_dir(dir_path: str, indent: int):
        info = dirs[dir_path]
        pad = "  " * indent
        lines.append(f'{pad}<Directory Id="{info["id"]}" Name="{_xml_escape(info["name"])}">')
        for comp_id, dir_id, file_id, source_rel, name in files_by_dir.get(info["id"], []):
            lines.append(f'{pad}  <Component Id="{comp_id}" Guid="*">')
            lines.append(f'{pad}    <File Id="{file_id}" Source="{_xml_escape(source_rel)}" '
                         f'Name="{_xml_escape(name)}" KeyPath="yes" />')
            lines.append(f'{pad}  </Component>')
        for child_path in children.get(info["id"], []):
            emit_dir(child_path, indent + 1)
        lines.append(f'{pad}</Directory>')

    for root_path in children.get("TARGETDIR", []):
        emit_dir(root_path, 3)

    lines.append('    </Directory>')
    lines.append('')

    # Registry components (placed under TARGETDIR)
    if reg_components:
        lines.append('    <DirectoryRef Id="TARGETDIR">')
        for rc in reg_components:
            lines.append(f'      <Component Id="{rc["cid"]}" Guid="*">')
            name_attr = f' Name="{_xml_escape(rc["name"])}"' if rc["name"] else ""
            lines.append(
                f'        <RegistryValue Root="{rc["root"]}" '
                f'Key="{_xml_escape(rc["key"])}"{name_attr} '
                f'Type="{rc["type"]}" Value="{_xml_escape(rc["value"])}" KeyPath="yes" />'
            )
            lines.append('      </Component>')
        lines.append('    </DirectoryRef>')
        lines.append('')

    # Feature referencing every component
    lines.append('    <Feature Id="MainFeature" Title="All Files" Level="1">')
    for comp in file_components:
        lines.append(f'      <ComponentRef Id="{comp[0]}" />')
    for rc in reg_components:
        lines.append(f'      <ComponentRef Id="{rc["cid"]}" />')
    lines.append('    </Feature>')
    lines.append('  </Product>')
    lines.append('</Wix>')
    return "\n".join(lines)
