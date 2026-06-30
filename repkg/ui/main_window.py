import ctypes

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .. import usn
from ..config import load_config, save_config
from ..differ import assemble, diff_registry
from ..engines import make_engine
from ..session import SESSION_EXT, load_session, save_session
from .theme import DARK, LIGHT, apply_theme
from .pages.changes_page import ChangesPage
from .pages.configure_page import ConfigurePage
from .pages.export_page import ExportPage
from .pages.snapshot_page import SnapshotPage

PAGE_CONFIGURE = 0
PAGE_SNAPSHOT = 1
PAGE_CHANGES = 2
PAGE_EXPORT = 3

STEPS = ["1. Configure", "2. Snapshot", "3. Review Changes", "4. Export"]


class _StepBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels: list[QLabel] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        for i, name in enumerate(STEPS):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            lbl.setStyleSheet("padding: 6px; border-radius: 4px;")
            lay.addWidget(lbl)
            self._labels.append(lbl)
            if i < len(STEPS) - 1:
                sep = QLabel("›")
                sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.addWidget(sep)

    def set_step(self, index: int):
        for i, lbl in enumerate(self._labels):
            if i == index:
                lbl.setStyleSheet("padding: 6px; border-radius: 4px; "
                                  "background: #1565c0; color: white; font-weight: bold;")
            elif i < index:
                lbl.setStyleSheet("padding: 6px; border-radius: 4px; "
                                  "background: #2e7d32; color: white;")
            else:
                lbl.setStyleSheet("padding: 6px; border-radius: 4px; "
                                  "background: #333; color: #888;")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RePKG — Setup Repackager")
        self.resize(1000, 720)
        self._changeset = None
        self._before = None
        self._after = None
        self._engine = None
        self._scan_roots = []
        self._scan_excl = []
        self._config = load_config()
        self._theme = DARK if self._config.get("theme", "dark") == "dark" else LIGHT
        self._build_menu()
        self._build_ui()
        self._check_admin()
        # Apply persisted theme + label
        apply_theme(QApplication.instance(), self._theme)
        self._theme_action.setText(
            "Switch to &Light Theme" if self._theme == DARK else "Switch to &Dark Theme"
        )

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        self._save_action = QAction("&Save Session…", self)
        self._save_action.setShortcut("Ctrl+S")
        self._save_action.setEnabled(False)
        self._save_action.triggered.connect(self._save_session)
        file_menu.addAction(self._save_action)

        load_action = QAction("&Load Session…", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._load_session)
        file_menu.addAction(load_action)

        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menubar.addMenu("&View")
        self._theme_action = QAction("Switch to &Light Theme", self)
        self._theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._theme_action)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        self._step_bar = _StepBar()
        root_layout.addWidget(self._step_bar)

        self._stack = QStackedWidget()
        root_layout.addWidget(self._stack)

        self._configure_page = ConfigurePage(config=self._config)
        self._snapshot_page = SnapshotPage()
        self._changes_page = ChangesPage()
        self._export_page = ExportPage()
        history = list(self._config.get("output_dir_history") or [])
        legacy = self._config.get("last_output_dir", "")  # migrate old single value
        if legacy and legacy not in history:
            history.insert(0, legacy)
        self._export_page.set_history(history)
        self._export_page.exported.connect(self._persist_config)

        self._stack.addWidget(self._configure_page)
        self._stack.addWidget(self._snapshot_page)
        self._stack.addWidget(self._changes_page)
        self._stack.addWidget(self._export_page)

        self._snapshot_page.snapshots_ready.connect(self._on_snapshots_ready)
        self._changes_page._next_btn.clicked.connect(self._go_export)

        nav = QHBoxLayout()
        self._back_btn = QPushButton("← Back")
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.hide()
        nav.addWidget(self._back_btn)
        nav.addStretch()
        self._start_btn = QPushButton("Start Before Snapshot →")
        self._start_btn.setFixedHeight(36)
        self._start_btn.clicked.connect(self._go_snapshot)
        nav.addWidget(self._start_btn)
        root_layout.addLayout(nav)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._go_to(PAGE_CONFIGURE)

    def _check_admin(self):
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            is_admin = False
        if not is_admin:
            self._status_bar.showMessage(
                "⚠  Not running as Administrator — some registry/system paths may be inaccessible."
            )

    # ---------- navigation ----------
    def _go_to(self, page: int):
        self._stack.setCurrentIndex(page)
        self._step_bar.set_step(page)
        self._back_btn.setVisible(page > PAGE_CONFIGURE)
        self._start_btn.setVisible(page == PAGE_CONFIGURE)

    def _go_back(self):
        current = self._stack.currentIndex()
        if current > PAGE_CONFIGURE:
            self._go_to(current - 1)

    def _go_snapshot(self):
        fs_roots = self._configure_page.get_fs_roots()
        exclusions = self._configure_page.get_exclusions()
        reg_hives = self._configure_page.get_reg_hives()
        settle = self._configure_page.get_settle_delay()

        engine_name = self._configure_page.get_scan_engine()
        if engine_name == "usn":
            ok, reason = usn.is_available(fs_roots)
            if not ok:
                engine_name = "snapshot"
                self._status_bar.showMessage(
                    f"USN unavailable ({reason}); using full snapshot.", 8000
                )
        self._engine = make_engine(engine_name)
        self._scan_roots = fs_roots
        self._scan_excl = exclusions

        self._persist_config()  # save custom paths/settings before a long scan
        self._snapshot_page.configure(self._engine, fs_roots, exclusions, reg_hives, settle)
        self._go_to(PAGE_SNAPSHOT)
        self._snapshot_page.start()

    def _build_changeset(self, before: dict, after: dict):
        file_triple = self._engine.file_changes(before, after, self._scan_roots, self._scan_excl)
        reg_triple = diff_registry(before.get("registry", {}), after.get("registry", {}))
        return assemble(file_triple, reg_triple)

    def _on_snapshots_ready(self, before: dict, after: dict):
        self._before = before
        self._after = after
        self._save_action.setEnabled(True)
        self._changeset = self._build_changeset(before, after)
        self._changes_page.load_changeset(self._changeset)
        self._go_to(PAGE_CHANGES)

    def _go_export(self):
        selected_files = self._changes_page.get_selected_files()
        selected_reg = self._changes_page.get_selected_reg_keys()
        self._export_page.configure(self._changeset, selected_files, selected_reg)
        self._go_to(PAGE_EXPORT)

    # ---------- session ----------
    def _save_session(self):
        if self._before is None or self._after is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Session", f"capture{SESSION_EXT}",
            f"RePKG Session (*{SESSION_EXT})"
        )
        if not path:
            return
        if not path.lower().endswith(SESSION_EXT):
            path += SESSION_EXT
        try:
            meta = {
                "engine": getattr(self._engine, "name", "snapshot"),
                "roots": self._scan_roots,
                "exclusions": self._scan_excl,
            }
            save_session(self._before, self._after, path, meta)
            self._status_bar.showMessage(f"Session saved: {path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def _load_session(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Session", "", f"RePKG Session (*{SESSION_EXT})"
        )
        if not path:
            return
        try:
            before, after, meta = load_session(path)
        except Exception as e:
            QMessageBox.critical(self, "Load Failed", str(e))
            return
        self._before = before
        self._after = after
        self._engine = make_engine(meta.get("engine", "snapshot"))
        self._scan_roots = meta.get("roots", [])
        self._scan_excl = meta.get("exclusions", [])
        self._save_action.setEnabled(True)
        self._changeset = self._build_changeset(before, after)
        self._changes_page.load_changeset(self._changeset)
        self._go_to(PAGE_CHANGES)
        self._status_bar.showMessage(f"Session loaded: {path}", 5000)

    # ---------- theme ----------
    def _toggle_theme(self):
        self._theme = LIGHT if self._theme == DARK else DARK
        apply_theme(QApplication.instance(), self._theme)
        self._theme_action.setText(
            "Switch to &Light Theme" if self._theme == DARK else "Switch to &Dark Theme"
        )
        self._persist_config()

    # ---------- config persistence ----------
    def _persist_config(self):
        cfg = self._configure_page.export_config()
        cfg["theme"] = self._theme
        cfg["output_dir_history"] = self._export_page.get_history()
        save_config(cfg)

    def closeEvent(self, event):
        self._persist_config()
        super().closeEvent(event)
