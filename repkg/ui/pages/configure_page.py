import os
import winreg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ... import usn
from ...snapshotter import DEFAULT_FS_EXCLUSIONS, DEFAULT_FS_ROOTS, DEFAULT_REG_HIVES, HIVE_NAMES

# Hives the user can pick when adding a custom registry root.
ADD_HIVE_OPTIONS = [
    "HKEY_LOCAL_MACHINE",
    "HKEY_CURRENT_USER",
    "HKEY_CLASSES_ROOT",
    "HKEY_USERS",
    "HKEY_CURRENT_CONFIG",
]

NAME_TO_HIVE = {
    "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
    "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
    "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
    "HKEY_USERS": winreg.HKEY_USERS,
    "HKEY_CURRENT_CONFIG": winreg.HKEY_CURRENT_CONFIG,
}

ALL_REG_HIVES = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE"),
    (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services"),
    (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control"),
    (winreg.HKEY_CURRENT_USER, r"Environment"),
]


def _reg_label(hive_handle, key_path: str) -> str:
    return f"{HIVE_NAMES.get(hive_handle, str(hive_handle))}\\{key_path}"


# Default registry list as (label, checked) pairs.
DEFAULT_REG_ENTRIES = [
    (_reg_label(h, k), (h, k) in DEFAULT_REG_HIVES) for h, k in ALL_REG_HIVES
]


class _AddRegDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Registry Key")
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self._hive = QComboBox()
        self._hive.addItems(ADD_HIVE_OPTIONS)
        row.addWidget(self._hive)
        row.addWidget(QLabel("\\"))
        self._path = QLineEdit()
        self._path.setPlaceholderText(r"SOFTWARE\\Vendor\\Product")
        row.addWidget(self._path, 1)
        lay.addLayout(row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def result_label(self) -> str:
        sub = self._path.text().strip().strip("\\")
        if not sub:
            return ""
        return f"{self._hive.currentText()}\\{sub}"


class ConfigurePage(QWidget):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self._build_ui()
        if config:
            self._apply_config(config)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setSpacing(12)

        layout.addWidget(QLabel("<h2>Configure Snapshot Scope</h2>"))
        desc = QLabel(
            "Select which filesystem paths and registry hives to monitor. "
            "Narrower scope = faster snapshots."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # --- Filesystem roots ---
        fs_group = QGroupBox("Filesystem Roots")
        fs_layout = QVBoxLayout(fs_group)
        self._fs_list = QListWidget()
        self._fs_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for root in DEFAULT_FS_ROOTS:
            self._add_checked_item(self._fs_list, root)
        fs_layout.addWidget(self._fs_list)
        fs_btns = QHBoxLayout()
        add_btn = QPushButton("Add Path…")
        add_btn.clicked.connect(lambda: self._browse_into(self._fs_list))
        fs_import_btn = QPushButton("Import from File…")
        fs_import_btn.setToolTip("Load paths from a .txt/.lst file (one per line)")
        fs_import_btn.clicked.connect(lambda: self._import_paths(self._fs_list, checkable=True))
        rm_btn = QPushButton("Remove Selected")
        rm_btn.clicked.connect(lambda: self._remove_selected(self._fs_list))
        fs_btns.addWidget(add_btn)
        fs_btns.addWidget(fs_import_btn)
        fs_btns.addWidget(rm_btn)
        fs_btns.addStretch()
        fs_layout.addLayout(fs_btns)
        layout.addWidget(fs_group)

        # --- Exclusions ---
        ex_group = QGroupBox("Exclusions (skipped during scan)")
        ex_layout = QVBoxLayout(ex_group)
        self._ex_list = QListWidget()
        self._ex_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._ex_list.setMaximumHeight(110)
        for ex in DEFAULT_FS_EXCLUSIONS:
            self._ex_list.addItem(QListWidgetItem(ex))
        ex_layout.addWidget(self._ex_list)
        ex_btns = QHBoxLayout()
        ex_add = QPushButton("Add Path…")
        ex_add.clicked.connect(self._add_exclusion)
        ex_import = QPushButton("Import from File…")
        ex_import.setToolTip("Load paths from a .txt/.lst file (one per line)")
        ex_import.clicked.connect(lambda: self._import_paths(self._ex_list, checkable=False))
        ex_rm = QPushButton("Remove Selected")
        ex_rm.clicked.connect(lambda: self._remove_selected(self._ex_list))
        ex_btns.addWidget(ex_add)
        ex_btns.addWidget(ex_import)
        ex_btns.addWidget(ex_rm)
        ex_btns.addStretch()
        ex_layout.addLayout(ex_btns)
        layout.addWidget(ex_group)

        # --- Registry keys ---
        reg_group = QGroupBox("Registry Keys")
        reg_layout = QVBoxLayout(reg_group)
        self._reg_list = QListWidget()
        self._reg_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for label, checked in DEFAULT_REG_ENTRIES:
            self._add_reg_item(label, checked)
        reg_layout.addWidget(self._reg_list)
        reg_btns = QHBoxLayout()
        reg_add = QPushButton("Add Key…")
        reg_add.clicked.connect(self._add_reg_key)
        reg_rm = QPushButton("Remove Selected")
        reg_rm.clicked.connect(lambda: self._remove_selected(self._reg_list))
        reg_def = QPushButton("Restore Defaults")
        reg_def.clicked.connect(self._restore_reg_defaults)
        reg_btns.addWidget(reg_add)
        reg_btns.addWidget(reg_rm)
        reg_btns.addWidget(reg_def)
        reg_btns.addStretch()
        reg_layout.addLayout(reg_btns)
        layout.addWidget(reg_group)

        # --- Options ---
        opt_group = QGroupBox("Options")
        opt_layout = QVBoxLayout(opt_group)

        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Scan engine:"))
        self._engine_combo = QComboBox()
        self._engine_combo.addItem("Full snapshot (any filesystem)", "snapshot")
        self._engine_combo.addItem("USN journal (NTFS, fast)", "usn")
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        engine_row.addWidget(self._engine_combo)
        engine_row.addStretch()
        opt_layout.addLayout(engine_row)

        self._engine_note = QLabel("")
        self._engine_note.setWordWrap(True)
        self._engine_note.setStyleSheet("color: #ff9800;")
        opt_layout.addWidget(self._engine_note)

        settle_row = QHBoxLayout()
        settle_row.addWidget(QLabel("Settle delay before after-snapshot:"))
        self._settle_spin = QSpinBox()
        self._settle_spin.setRange(0, 300)
        self._settle_spin.setValue(5)
        self._settle_spin.setSuffix(" s")
        settle_row.addWidget(self._settle_spin)
        settle_row.addStretch()
        opt_layout.addLayout(settle_row)

        layout.addWidget(opt_group)

        layout.addStretch()

    # --- helpers ---
    def _add_checked_item(self, widget: QListWidget, text: str):
        item = QListWidgetItem(text)
        item.setCheckState(Qt.CheckState.Checked)
        widget.addItem(item)

    def _browse_into(self, widget: QListWidget):
        path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            self._add_checked_item(widget, os.path.normpath(path))

    def _add_exclusion(self):
        path = QFileDialog.getExistingDirectory(self, "Select Directory to Exclude")
        if path:
            self._ex_list.addItem(QListWidgetItem(os.path.normpath(path)))

    def _remove_selected(self, widget: QListWidget):
        for item in widget.selectedItems():
            widget.takeItem(widget.row(item))

    # --- engine ---
    def _on_engine_changed(self):
        if self._engine_combo.currentData() != "usn":
            self._engine_note.setText("")
            return
        ok, reason = usn.is_available(self.get_fs_roots() or DEFAULT_FS_ROOTS)
        if ok:
            self._engine_note.setText(
                "USN journal active. Captures only changed files — much faster on large roots. "
                "Runs whole-volume, so unrelated background changes may appear (use exclusions / noise filter)."
            )
        else:
            self._engine_note.setText(
                f"USN journal unavailable: {reason}. Will fall back to full snapshot at scan time."
            )

    # --- registry helpers ---
    def _add_reg_item(self, label: str, checked: bool):
        item = QListWidgetItem(label)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._reg_list.addItem(item)

    def _existing_reg(self) -> set:
        return {self._reg_list.item(i).text() for i in range(self._reg_list.count())}

    def _add_reg_key(self):
        dlg = _AddRegDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        label = dlg.result_label()
        if not label:
            return
        if label in self._existing_reg():
            QMessageBox.information(self, "Already Present", f"{label} is already listed.")
            return
        self._add_reg_item(label, True)

    def _restore_reg_defaults(self):
        self._reg_list.clear()
        for label, checked in DEFAULT_REG_ENTRIES:
            self._add_reg_item(label, checked)

    def _existing_paths(self, widget: QListWidget) -> set:
        return {widget.item(i).text() for i in range(widget.count())}

    def _import_paths(self, widget: QListWidget, checkable: bool):
        from PySide6.QtWidgets import QMessageBox
        fpath, _ = QFileDialog.getOpenFileName(
            self, "Import Paths", "", "Path lists (*.txt *.lst);;All files (*.*)"
        )
        if not fpath:
            return
        try:
            with open(fpath, "r", encoding="utf-8-sig", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            QMessageBox.critical(self, "Import Failed", str(e))
            return

        existing = self._existing_paths(widget)
        added = 0
        for line in lines:
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            entry = os.path.normpath(entry)
            if entry in existing:
                continue
            existing.add(entry)
            if checkable:
                self._add_checked_item(widget, entry)
            else:
                widget.addItem(QListWidgetItem(entry))
            added += 1
        QMessageBox.information(
            self, "Import Complete", f"Added {added} path(s) from file."
        )

    # --- config persistence ---
    def _apply_config(self, cfg: dict):
        fs_roots = cfg.get("fs_roots")
        if fs_roots:
            self._fs_list.clear()
            for entry in fs_roots:
                item = QListWidgetItem(entry.get("path", ""))
                item.setCheckState(
                    Qt.CheckState.Checked if entry.get("checked", True)
                    else Qt.CheckState.Unchecked
                )
                self._fs_list.addItem(item)

        exclusions = cfg.get("exclusions")
        if exclusions is not None:
            self._ex_list.clear()
            for ex in exclusions:
                self._ex_list.addItem(QListWidgetItem(ex))

        reg_hives = cfg.get("reg_hives")
        if reg_hives:
            self._reg_list.clear()
            if isinstance(reg_hives, dict):  # legacy format: {label: checked}
                for label, checked in reg_hives.items():
                    self._add_reg_item(label, bool(checked))
            else:  # list of {"label", "checked"}
                for entry in reg_hives:
                    self._add_reg_item(entry.get("label", ""), entry.get("checked", True))

        settle = cfg.get("settle_delay")
        if settle is not None:
            self._settle_spin.setValue(int(settle))

        engine = cfg.get("scan_engine")
        if engine:
            idx = self._engine_combo.findData(engine)
            if idx >= 0:
                self._engine_combo.setCurrentIndex(idx)

    def export_config(self) -> dict:
        return {
            "fs_roots": [
                {
                    "path": self._fs_list.item(i).text(),
                    "checked": self._fs_list.item(i).checkState() == Qt.CheckState.Checked,
                }
                for i in range(self._fs_list.count())
            ],
            "exclusions": [self._ex_list.item(i).text() for i in range(self._ex_list.count())],
            "reg_hives": [
                {
                    "label": self._reg_list.item(i).text(),
                    "checked": self._reg_list.item(i).checkState() == Qt.CheckState.Checked,
                }
                for i in range(self._reg_list.count())
            ],
            "settle_delay": self._settle_spin.value(),
            "scan_engine": self._engine_combo.currentData(),
        }

    # --- getters ---
    def get_fs_roots(self) -> list[str]:
        return [
            self._fs_list.item(i).text()
            for i in range(self._fs_list.count())
            if self._fs_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def get_exclusions(self) -> list[str]:
        return [self._ex_list.item(i).text() for i in range(self._ex_list.count())]

    def get_reg_hives(self) -> list[tuple]:
        result = []
        for i in range(self._reg_list.count()):
            item = self._reg_list.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            label = item.text()
            name, _, sub = label.partition("\\")
            handle = NAME_TO_HIVE.get(name)
            if handle is not None:
                result.append((handle, sub))
        return result

    def get_settle_delay(self) -> int:
        return self._settle_spin.value()

    def get_scan_engine(self) -> str:
        return self._engine_combo.currentData()
