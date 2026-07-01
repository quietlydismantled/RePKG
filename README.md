# RePKG — Setup Repackager

**Are you tired of installers barging into your system like they own the place?**

Introducing **RePKG**: the astonishing, suspiciously useful, Windows-only setup repackaging contraption that watches an installer rummage through your filesystem and registry, then helps you bottle up the aftermath like a tiny forensic souvenir!!!

That's right: RePKG takes a snapshot **before** you run an installer, another snapshot **after**, compares the wreckage, and lets you decide what gets exported into a portable, redistributable package. Files! Registry values! Tiny clues left behind by setup wizards with commitment issues!

It's the classic install monitor / repackager workflow — think AppDeploy Repackager, Wise, InstallRite, and other names that smell faintly of beige office carpet — rebuilt as a modern [PySide6](https://pypi.org/project/PySide6/) app with an optional fast NTFS change-journal engine and direct **WiX/MSI** output.

**Installers go in. Diffs come out. Productivity confetti falls gently from the ceiling.**

---

## Features You Probably Could Have Scripted, But Look, Buttons!!!

- **Before/after snapshotting** of the filesystem and Windows registry, so installers can stop acting like mysterious little gremlins with diplomatic immunity.
- **Two scan engines**, for users who believe one method of surveillance simply lacks theatrical range:
  - **Full snapshot** — walks the configured roots and hashes every file using MD5 + size + mtime. Works on any filesystem. It is thorough. It is patient. It has sensible shoes.
  - **USN journal** — reads the NTFS change journal to capture *only* the files that changed instead of re-walking everything like a Victorian detective with a lantern. Much faster on large roots. Requires NTFS + Administrator, and falls back to full snapshot automatically when unavailable, preserving dignity during moments of filesystem disappointment.
- **Configurable scope** — choose filesystem roots, exclusions, and registry hives to monitor. Import path lists from `.txt` or `.lst` files, add custom registry keys, and persist your setup between runs like a civilized person with preferences.
- **Change review** — a categorized, checkable tree for Files / Shortcuts / Registry / Services, with search, size totals, and a one-click **noise filter** that hides and deselects junk like temp files, logs, MUICache, RecentDocs, prefetch, and other digital pocket lint.
- **Multiple export artifacts** from one capture. One button, several useful things, absolutely no promise that Windows will behave afterward.
  - a mirrored **file tree** of captured files (`FILES/C/...`),
  - a **`registry_changes.reg`** file you can re-import,
  - a **`manifest.json`** describing every exported item,
  - a **`setup.wxs`** WiX v3 source for compiling a real **MSI** installer, like an actual grown-up.
- **Saveable sessions** — store a before+after capture to a single compressed `.repkg` file and re-open it later to re-diff and re-export. Future-you deserves evidence, snacks, and maybe a chair.
- **Settle delay** to let background writes finish before the after-snapshot, since installers sometimes keep scribbling after they say they're done. Rude, but expected.
- Dark/light themes, a guided 4-step wizard, and an admin-privilege warning. Even chaos deserves a status bar and a tasteful palette.

---

## How It Works: Four Steps to Controlled Installer Surveillance

RePKG walks you through a four-step wizard:

```text
1. Configure  ›  2. Snapshot  ›  3. Review Changes  ›  4. Export
```

1. **Configure** — pick the filesystem roots, exclusions, registry hives, scan engine, and settle delay. This is where you tell RePKG where to stare, and how intensely.
2. **Snapshot** — RePKG takes the *before* snapshot. You then run your installer and allow it to perform its little dance. When it finishes, click **Continue**; after an optional settle delay, RePKG takes the *after* snapshot.
3. **Review Changes** — the diff appears as a tree. Tick the files and registry values you want to keep. Deletions are listed but unchecked by default, which feels appropriate for a feature that could otherwise become a tiny deployment flamethrower.
4. **Export** — choose an output folder and write the package: files, `.reg`, `manifest.json`, and `setup.wxs`.

Under the hood, a snapshot is a dictionary of `path -> {size, mtime, md5}` for files — or a USN checkpoint when the fast lane is available — plus `key -> {type, data, ...}` for registry values. The differ compares the two snapshots into added / modified / deleted sets, and the exporter copies the selected files while emitting the `.reg` and WiX sources.

In less polite terms: RePKG watches an installer sneeze all over Windows, then hands you a clipboard and asks, “Which of these droplets are business-critical?”

---

## Output Package Layout: The Evidence Locker

After an export, the output directory contains:

```text
output/
├── FILES/                  # captured files, mirrored by drive (C\Program Files\...)
│   └── C\...
├── registry_changes.reg    # importable .reg of the selected registry changes
├── manifest.json           # machine-readable record of everything exported
└── setup.wxs               # WiX v3 source — compile to an MSI (see below)
```

That's right: one capture can produce a file tree, a registry file, a manifest, and WiX source. Four artifacts enter the ring. Your deployment process leaves slightly less chaotic.

### Building an MSI from `setup.wxs`

`setup.wxs` is a [WiX Toolset](https://wixtoolset.org/) v3 source. To build an installer with WiX v3 (`candle` / `light`) from the output directory:

```powershell
candle setup.wxs
light setup.wixobj -o Repackaged.msi
```

> **Important grown-up note:** the generated source uses a placeholder `UpgradeCode` (`{PUT-A-STABLE-GUID-HERE}`). Replace it with a real, stable GUID before shipping an upgradeable product. Otherwise your upgrade story may become interpretive dance.

---

## Requirements: Before the Show Can Begin

- **Windows** — the app uses `winreg` and Win32 APIs, so it is Windows-only. Linux and macOS may watch from the lobby.
- **Python 3.10+** — the code uses `X | Y` type unions and modern syntax. Ancient Python must remain in the museum.
- **[PySide6](https://pypi.org/project/PySide6/) ≥ 6.6** — see `requirements.txt`. The rectangles require a stage crew.
- **Administrator privileges** are recommended. Many registry and system paths are inaccessible otherwise, and the **USN journal engine requires admin**. The app shows a warning in the status bar when not elevated, sparing you the classic Windows guessing game: "is it broken, or am I simply insufficiently powerful?"

---

## Installation & Running: Summon the Rectangle

### From source

```powershell
git clone https://github.com/quietlydismantled/RePKG.git
cd RePKG
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Run from an **elevated** terminal to capture protected paths and use the USN engine. Non-elevated mode still exists, but Windows will absolutely keep some secrets from you like a tiny corporate dragon.

### Prebuilt executable

A standalone build is included at [`dist/RePKG.exe`](dist/RePKG.exe). Run it directly — right-click → *Run as administrator* recommended — and behold: a repackaging appliance in window form.

### Building the executable yourself

The project ships a [PyInstaller](https://pyinstaller.org/) spec:

```powershell
pip install pyinstaller
pyinstaller RePKG.spec
```

The result is a single-file, windowed executable in `dist/`. Incredible. You made a program into one program.

---

## Project Layout: The Tiny Factory Floor

```text
main.py                 # entry point — boots the Qt app and main window
repkg/
├── config.py           # persistent JSON config in %APPDATA%\RePKG\config.json
├── snapshotter.py      # full filesystem + registry snapshotting (walk engine)
├── usn.py              # NTFS USN change-journal reader (ctypes, no pywin32)
├── engines.py          # WalkEngine / UsnEngine — unified capture + diff API
├── differ.py           # snapshot diffing → ChangeSet (added/modified/deleted)
├── filters.py          # noise patterns (temp/log files, MUICache, etc.)
├── exporter.py         # copy files, emit .reg, manifest.json, and WiX setup.wxs
├── session.py          # save/load a capture as a compressed .repkg file
└── ui/
    ├── main_window.py  # 4-step wizard, menu, session + theme handling
    ├── theme.py        # dark/light Fusion palettes
    └── pages/
        ├── configure_page.py  # step 1 — scope, engine, options
        ├── snapshot_page.py   # step 2 — before/after capture (threaded)
        ├── changes_page.py    # step 3 — reviewable change tree
        └── export_page.py     # step 4 — output dir + export (threaded)
```

It's all there: snapshotters, diff goblins, filters, exporters, sessions, and UI pages. Like a tiny warehouse where every box is labeled and at least one forklift has opinions.

---

## Notes & Caveats, Also Known as “Windows Happened”

- **Run installers in isolation.** The diff captures *everything* that changed during the window, so unrelated background activity — Windows Update, antivirus, telemetry, mysterious helper processes with names like `UpdaterServiceHelperHostThing.exe` — can wander into frame wearing a fake mustache. Use exclusions and the noise filter, keep the scope narrow, and close other apps for the cleanest capture. The USN engine in particular records whole-volume changes with the restraint of a raccoon in a snack aisle.
- **Registry data** is captured from the configured hives via value enumeration. Permissions you lack will silently be skipped; Windows security boundaries remain unmoved by enthusiasm, confidence, or motivational chanting.
- RePKG excludes its own temp artifacts (`repkg_*.json`, `*.repkg`) from scans. Eating your own breadcrumbs is not a deployment strategy, no matter what that one legacy script says.
- The `.repkg` session format is versioned. Current version: 2. Version 1 still loads, in a touching display of selective respect for our elders.

---

## TL;DR, For Those of You Who Never Made It This Far and Will Never Read This

RePKG watches what an installer changes, shows you the evidence, and lets you export the useful bits without manually spelunking through `Program Files`, registry hives, and whatever haunted drawer Windows keeps services in.

In slightly more responsible words:

1. Configure what to watch.
2. Take the before snapshot.
3. Run the installer and let it do its little puppet show.
4. Take the after snapshot.
5. Review the diff like a tiny software detective.
6. Export files, registry changes, a manifest, and WiX source for MSI-building glory.

It is not magic. It is not psychic. It will not stop a noisy machine from producing noisy results. But it *will* help turn “what in the absolute registry hive did that setup wizard just do?” into “ah, here are the changes, neatly checkable, filterable, and ready to package.”

Use it in a clean-ish environment (READ: SRSLY run this in a clean vm snapshot). Keep the scope tight. Read the diff. Trust nothing wearing the word `Updater` in a filename.

---

## License

No license file is currently included in this repository.

Which means, for now, the licensing situation is doing that thing where it stands in the corner wearing sunglasses and refusing to elaborate.
