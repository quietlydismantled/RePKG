import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...differ import ChangeSet
from ... import filters

_COLOR = {
    "Added":    QColor("#4caf50"),
    "Modified": QColor("#ff9800"),
    "Deleted":  QColor("#f44336"),
}
_COLOR_DELETED_FG = QColor("#666666")

ROLE_KEY   = Qt.ItemDataRole.UserRole       # leaf identifier (col 0)
ROLE_KIND  = Qt.ItemDataRole.UserRole       # "file" / "reg" (col 1)
ROLE_NOISE = Qt.ItemDataRole.UserRole + 1   # bool (col 0)
ROLE_SIZE  = Qt.ItemDataRole.UserRole + 2   # int bytes (col 0)


def _split_path(path: str) -> list[str]:
    parts = []
    while True:
        head, tail = os.path.split(path)
        if tail:
            parts.append(tail)
            path = head
        else:
            if head:
                parts.append(head)
            break
    parts.reverse()
    return parts


def _split_reg(key: str) -> list[str]:
    return [p for p in key.split("\\") if p]


def _fmt_size(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{n} B"


def _get_or_create_child(parent: QTreeWidgetItem, text: str) -> QTreeWidgetItem:
    for i in range(parent.childCount()):
        if parent.child(i).text(0) == text:
            return parent.child(i)
    item = QTreeWidgetItem(parent, [text, "", ""])
    item.setCheckState(0, Qt.CheckState.Checked)
    return item


def _set_subtree_check(item: QTreeWidgetItem, state: Qt.CheckState):
    for i in range(item.childCount()):
        child = item.child(i)
        if not child.isDisabled():
            child.setCheckState(0, state)
            _set_subtree_check(child, state)


def _sync_check_upward(item: QTreeWidgetItem):
    parent = item.parent()
    while parent is not None and parent.parent() is not None:
        enabled = [
            parent.child(i)
            for i in range(parent.childCount())
            if not parent.child(i).isDisabled()
        ]
        if enabled:
            states = {c.checkState(0) for c in enabled}
            if states == {Qt.CheckState.Checked}:
                parent.setCheckState(0, Qt.CheckState.Checked)
            elif Qt.CheckState.Checked in states or Qt.CheckState.PartiallyChecked in states:
                parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
            else:
                parent.setCheckState(0, Qt.CheckState.Unchecked)
        parent = parent.parent()


def _partition(items: dict, pred) -> tuple[dict, dict]:
    yes, no = {}, {}
    for k, v in items.items():
        (yes if pred(k) else no)[k] = v
    return yes, no


class ChangesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self._title = QLabel("<h2>Changes Detected</h2>")
        layout.addWidget(self._title)

        self._summary = QLabel("")
        layout.addWidget(self._summary)

        # Search + noise row
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by path or key…")
        self._search.textChanged.connect(self._refilter)
        search_row.addWidget(self._search, 1)
        self._noise_cb = QCheckBox("Hide && deselect noise")
        self._noise_cb.setToolTip("Temp files, logs, MUICache, RecentDocs, prefetch, etc.")
        self._noise_cb.toggled.connect(self._on_noise_toggled)
        search_row.addWidget(self._noise_cb)
        layout.addLayout(search_row)

        # Toolbar
        toolbar = QHBoxLayout()
        for label, slot in (
            ("Expand All", self._tree_expand_all),
            ("Collapse All", self._tree_collapse_all),
            ("Select All", lambda: self._set_all(Qt.CheckState.Checked)),
            ("Deselect All", lambda: self._set_all(Qt.CheckState.Unchecked)),
        ):
            b = QPushButton(label)
            b.clicked.connect(slot)
            toolbar.addWidget(b)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Path / Key", "Change", "Details"])
        self._tree.setColumnWidth(0, 500)
        self._tree.setColumnWidth(1, 80)
        self._tree.setColumnWidth(2, 240)
        self._tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._tree)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._next_btn = QPushButton("Next: Export →")
        self._next_btn.setFixedHeight(36)
        btn_row.addWidget(self._next_btn)
        layout.addLayout(btn_row)

    # ---------- tree construction ----------
    def load_changeset(self, cs: ChangeSet):
        self._tree.blockSignals(True)
        self._tree.clear()
        self._search.clear()
        self._noise_cb.setChecked(False)

        # Partition shortcuts out of files, services out of registry
        is_lnk = lambda p: p.lower().endswith(".lnk")
        is_svc = lambda k: "\\services\\" in k.lower()

        f_add_lnk, f_add = _partition(cs.files_added, is_lnk)
        f_mod_lnk, f_mod = _partition(cs.files_modified, is_lnk)
        f_del_lnk, f_del = _partition(cs.files_deleted, is_lnk)

        r_add_svc, r_add = _partition(cs.reg_added, is_svc)
        r_mod_svc, r_mod = _partition(cs.reg_modified, is_svc)
        r_del_svc, r_del = _partition(cs.reg_deleted, is_svc)

        self._build_category("Files", f_add, f_mod, f_del, "file")
        self._build_category("Shortcuts", f_add_lnk, f_mod_lnk, f_del_lnk, "file")
        self._build_category("Registry", r_add, r_mod, r_del, "reg")
        self._build_category("Services", r_add_svc, r_mod_svc, r_del_svc, "reg")

        self._tree.blockSignals(False)
        self._update_summary()

    def _build_category(self, label, added, modified, deleted, kind):
        total = len(added) + len(modified) + len(deleted)
        if total == 0:
            return
        root = QTreeWidgetItem(self._tree, [f"{label} ({total:,})", "", ""])
        root.setExpanded(True)
        for change_label, items, deletion in (
            ("Added", added, False),
            ("Modified", modified, False),
            ("Deleted", deleted, True),
        ):
            if not items:
                continue
            group = QTreeWidgetItem(root, [f"{change_label} ({len(items):,})", "", ""])
            group.setExpanded(True)
            group.setCheckState(
                0, Qt.CheckState.Unchecked if deletion else Qt.CheckState.Checked
            )
            for key, meta in items.items():
                self._insert_leaf(group, key, meta, change_label, deletion, kind)

    def _insert_leaf(self, group, key, meta, change_label, deletion, kind):
        parts = _split_path(key) if kind == "file" else _split_reg(key)
        parent = group
        for part in parts[:-1]:
            parent = _get_or_create_child(parent, part)
            parent.setExpanded(False)

        detail, size = self._detail_and_size(kind, change_label, meta)
        leaf_text = parts[-1] if parts else key
        if kind == "reg" and not leaf_text:
            leaf_text = "(Default)"
        leaf = QTreeWidgetItem(parent, [leaf_text, change_label, detail])
        leaf.setData(0, ROLE_KEY, key)
        leaf.setData(1, ROLE_KIND, kind)
        leaf.setData(0, ROLE_SIZE, size)
        is_noise = (
            filters.is_noise_file(key) if kind == "file" else filters.is_noise_reg(key)
        )
        leaf.setData(0, ROLE_NOISE, is_noise)
        leaf.setForeground(1, _COLOR.get(change_label, QColor("white")))

        if deletion:
            leaf.setCheckState(0, Qt.CheckState.Unchecked)
            leaf.setDisabled(True)
            for col in range(3):
                leaf.setForeground(col, _COLOR_DELETED_FG)
        else:
            leaf.setCheckState(0, Qt.CheckState.Checked)

    def _detail_and_size(self, kind, change_label, meta):
        if kind == "file":
            if change_label == "Modified":
                size = meta.get("after", {}).get("size", 0)
            elif change_label == "Added":
                size = meta.get("size", 0)
            else:
                size = 0
            return (_fmt_size(size) if size else ""), size
        else:
            if change_label == "Modified":
                before = str(meta.get("before", {}).get("data", ""))
                after = str(meta.get("after", {}).get("data", ""))
                return f"{before[:30]} → {after[:30]}", 0
            elif change_label == "Added":
                return str(meta.get("data", ""))[:60], 0
            return "", 0

    # ---------- check propagation ----------
    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != 0 or item.isDisabled():
            return
        self._tree.blockSignals(True)
        state = item.checkState(0)
        _set_subtree_check(item, state)
        _sync_check_upward(item)
        self._tree.blockSignals(False)
        self._update_summary()

    def _set_all(self, state: Qt.CheckState):
        self._tree.blockSignals(True)
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            _set_subtree_check(root.child(i), state)
            root.child(i).setCheckState(0, state)
        self._tree.blockSignals(False)
        self._update_summary()

    def _tree_expand_all(self):
        self._tree.expandAll()

    def _tree_collapse_all(self):
        self._tree.collapseAll()
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setExpanded(True)

    # ---------- filtering ----------
    def _walk_leaves(self):
        stack = []
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            stack.append(root.child(i))
        while stack:
            it = stack.pop()
            if it.childCount() == 0:
                yield it
            else:
                for i in range(it.childCount()):
                    stack.append(it.child(i))

    def _on_noise_toggled(self, on: bool):
        self._tree.blockSignals(True)
        for leaf in self._walk_leaves():
            if leaf.isDisabled():
                continue
            if leaf.data(0, ROLE_NOISE):
                leaf.setCheckState(
                    0, Qt.CheckState.Unchecked if on else Qt.CheckState.Checked
                )
                _sync_check_upward(leaf)
        self._tree.blockSignals(False)
        self._refilter()
        self._update_summary()

    def _refilter(self):
        text = self._search.text().strip().lower()
        hide_noise = self._noise_cb.isChecked()

        # First: decide leaf visibility
        for leaf in self._walk_leaves():
            key = leaf.data(0, ROLE_KEY) or leaf.text(0)
            matches = (not text) or (text in str(key).lower())
            noisy = hide_noise and bool(leaf.data(0, ROLE_NOISE))
            leaf.setHidden(not matches or noisy)

        # Then: hide parents with no visible children
        def _resolve(item: QTreeWidgetItem) -> bool:
            if item.childCount() == 0:
                return not item.isHidden()
            any_visible = False
            for i in range(item.childCount()):
                if _resolve(item.child(i)):
                    any_visible = True
            item.setHidden(not any_visible)
            return any_visible

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            _resolve(root.child(i))

    # ---------- summary / totals ----------
    def _update_summary(self):
        n_files = n_reg = 0
        total_bytes = 0
        for leaf in self._walk_leaves():
            if leaf.checkState(0) != Qt.CheckState.Checked:
                continue
            kind = leaf.data(1, ROLE_KIND)
            if kind == "file":
                n_files += 1
                total_bytes += int(leaf.data(0, ROLE_SIZE) or 0)
            elif kind == "reg":
                n_reg += 1
        self._summary.setText(
            f"Selected: {n_files:,} files ({_fmt_size(total_bytes)})  |  "
            f"{n_reg:,} registry values"
        )

    # ---------- selection getters ----------
    def _collect_checked(self, kind: str) -> set:
        return {
            leaf.data(0, ROLE_KEY)
            for leaf in self._walk_leaves()
            if leaf.data(1, ROLE_KIND) == kind
            and leaf.checkState(0) == Qt.CheckState.Checked
            and leaf.data(0, ROLE_KEY)
        }

    def get_selected_files(self) -> set:
        return self._collect_checked("file")

    def get_selected_reg_keys(self) -> set:
        return self._collect_checked("reg")
