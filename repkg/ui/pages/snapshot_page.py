import os
import tempfile
from typing import Optional

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...snapshotter import (
    snapshot_filesystem,
    snapshot_registry,
    save_snapshot,
)


class _SnapshotWorker(QThread):
    # NOTE: do not name a signal `finished`/`started` — those collide with
    # QThread's built-in signals and deliver out-of-order vs `progress`.
    progress = Signal(str, int)  # (path, running_count)
    result_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, fs_roots, fs_exclusions, reg_hives):
        super().__init__()
        self._fs_roots = fs_roots
        self._fs_exclusions = fs_exclusions
        self._reg_hives = reg_hives
        self._count = 0

    def _tick(self, path: str):
        self._count += 1
        # Throttle UI updates — emit every 25 files
        if self._count % 25 == 0:
            self.progress.emit(path, self._count)

    def run(self):
        try:
            fs = snapshot_filesystem(
                self._fs_roots,
                self._fs_exclusions,
                progress_cb=self._tick,
            )
            reg = snapshot_registry(
                self._reg_hives,
                progress_cb=lambda p: self.progress.emit(p, self._count),
            )
            self.result_ready.emit({"filesystem": fs, "registry": reg})
        except Exception as e:
            self.error.emit(str(e))


class SnapshotPage(QWidget):
    # before, after — emitted when both snapshots complete
    snapshots_ready = Signal(dict, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fs_roots = []
        self._fs_exclusions = []
        self._reg_hives = []
        self._settle_delay = 0
        self._before: Optional[dict] = None
        self._worker: Optional[_SnapshotWorker] = None
        self._settle_remaining = 0
        self._settle_timer = QTimer(self)
        self._settle_timer.setInterval(1000)
        self._settle_timer.timeout.connect(self._settle_tick)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._title = QLabel("<h2>Taking Snapshot…</h2>")
        layout.addWidget(self._title)

        self._status_label = QLabel("Preparing…")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._count_label = QLabel("")
        layout.addWidget(self._count_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        layout.addWidget(self._progress)

        self._install_frame = QFrame()
        self._install_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._install_frame.setStyleSheet(
            "QFrame { background: palette(alternate-base); border: 1px solid #555; border-radius: 6px; }"
        )
        install_layout = QVBoxLayout(self._install_frame)
        install_lbl = QLabel(
            "<b>Before-snapshot complete.</b><br><br>"
            "Run your installer now. When it finishes, click <b>Continue</b> below."
        )
        install_lbl.setWordWrap(True)
        install_layout.addWidget(install_lbl)
        self._install_frame.hide()
        layout.addWidget(self._install_frame)

        self._continue_btn = QPushButton("Continue →  (After Snapshot)")
        self._continue_btn.setFixedHeight(36)
        self._continue_btn.hide()
        self._continue_btn.clicked.connect(self._begin_settle)
        layout.addWidget(self._continue_btn)

        layout.addStretch()

    def configure(self, fs_roots, fs_exclusions, reg_hives, settle_delay=0):
        self._fs_roots = fs_roots
        self._fs_exclusions = fs_exclusions
        self._reg_hives = reg_hives
        self._settle_delay = settle_delay

    def start(self):
        self._title.setText("<h2>Before Snapshot</h2>")
        self._status_label.setText("Scanning filesystem and registry…")
        self._count_label.setText("")
        self._progress.setRange(0, 0)
        self._progress.show()
        self._install_frame.hide()
        self._continue_btn.hide()

        self._worker = _SnapshotWorker(self._fs_roots, self._fs_exclusions, self._reg_hives)
        self._worker.progress.connect(self._on_progress)
        self._worker.result_ready.connect(self._on_before_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str, count: int):
        self._status_label.setText(msg[-80:] if len(msg) > 80 else msg)
        self._count_label.setText(f"{count:,} files scanned")

    def _on_before_done(self, snapshot: dict):
        self._before = snapshot
        tmp = os.path.join(tempfile.gettempdir(), "repkg_before.json")
        save_snapshot(snapshot, tmp)

        self._title.setText("<h2>Before Snapshot Complete</h2>")
        self._progress.hide()
        self._count_label.setText("")
        self._status_label.setText(
            f"Captured {len(snapshot['filesystem']):,} files  |  "
            f"{len(snapshot['registry']):,} registry values"
        )
        self._install_frame.show()
        self._continue_btn.show()

    def _begin_settle(self):
        self._install_frame.hide()
        self._continue_btn.hide()
        if self._settle_delay <= 0:
            self._start_after_snapshot()
            return
        self._settle_remaining = self._settle_delay
        self._title.setText("<h2>Settling…</h2>")
        self._progress.hide()
        self._status_label.setText(
            f"Waiting {self._settle_remaining}s for background writes to finish…"
        )
        self._settle_timer.start()

    def _settle_tick(self):
        self._settle_remaining -= 1
        if self._settle_remaining <= 0:
            self._settle_timer.stop()
            self._start_after_snapshot()
        else:
            self._status_label.setText(
                f"Waiting {self._settle_remaining}s for background writes to finish…"
            )

    def _start_after_snapshot(self):
        self._title.setText("<h2>After Snapshot</h2>")
        self._status_label.setText("Scanning filesystem and registry…")
        self._count_label.setText("")
        self._progress.setRange(0, 0)
        self._progress.show()

        self._worker = _SnapshotWorker(self._fs_roots, self._fs_exclusions, self._reg_hives)
        self._worker.progress.connect(self._on_progress)
        self._worker.result_ready.connect(self._on_after_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_after_done(self, after: dict):
        self._progress.hide()
        self._count_label.setText("")
        self._status_label.setText(
            f"After snapshot: {len(after['filesystem']):,} files  |  "
            f"{len(after['registry']):,} registry values"
        )
        self.snapshots_ready.emit(self._before, after)

    def _on_error(self, msg: str):
        self._progress.hide()
        self._status_label.setText(f"<span style='color:red'>Error: {msg}</span>")
