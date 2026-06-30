import os
import winreg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...snapshotter import DEFAULT_FS_EXCLUSIONS, DEFAULT_FS_ROOTS, DEFAULT_REG_HIVES, HIVE_NAMES

ALL_REG_HIVES = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE"),
    (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services"),
    (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control"),
    (winreg.HKEY_CURRENT_USER, r"Environment"),
]


class ConfigurePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

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
        rm_btn = QPushButton("Remove Selected")
        rm_btn.clicked.connect(lambda: self._remove_selected(self._fs_list))
        fs_btns.addWidget(add_btn)
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
        ex_rm = QPushButton("Remove Selected")
        ex_rm.clicked.connect(lambda: self._remove_selected(self._ex_list))
        ex_btns.addWidget(ex_add)
        ex_btns.addWidget(ex_rm)
        ex_btns.addStretch()
        ex_layout.addLayout(ex_btns)
        layout.addWidget(ex_group)

        # --- Registry hives ---
        reg_group = QGroupBox("Registry Hives")
        reg_layout = QVBoxLayout(reg_group)
        self._reg_checks: list[tuple[QCheckBox, tuple]] = []
        for hive_handle, key_path in ALL_REG_HIVES:
            hive_name = HIVE_NAMES.get(hive_handle, str(hive_handle))
            cb = QCheckBox(f"{hive_name}\\{key_path}")
            cb.setChecked((hive_handle, key_path) in DEFAULT_REG_HIVES)
            reg_layout.addWidget(cb)
            self._reg_checks.append((cb, (hive_handle, key_path)))
        layout.addWidget(reg_group)

        # --- Settle delay ---
        settle_group = QGroupBox("Options")
        settle_layout = QHBoxLayout(settle_group)
        settle_layout.addWidget(QLabel("Settle delay before after-snapshot:"))
        self._settle_spin = QSpinBox()
        self._settle_spin.setRange(0, 300)
        self._settle_spin.setValue(5)
        self._settle_spin.setSuffix(" s")
        settle_layout.addWidget(self._settle_spin)
        settle_layout.addStretch()
        layout.addWidget(settle_group)

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
        return [hive for cb, hive in self._reg_checks if cb.isChecked()]

    def get_settle_delay(self) -> int:
        return self._settle_spin.value()
