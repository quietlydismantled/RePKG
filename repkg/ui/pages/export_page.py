from __future__ import annotations

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...differ import ChangeSet
from ...exporter import export


class _ExportWorker(QThread):
    progress = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, changeset, selected_files, selected_reg_keys, output_dir):
        super().__init__()
        self._cs = changeset
        self._files = selected_files
        self._reg = selected_reg_keys
        self._out = output_dir

    def run(self):
        try:
            manifest = export(
                self._cs,
                self._files,
                self._reg,
                self._out,
                progress_cb=lambda m: self.progress.emit(m),
            )
            self.finished.emit(manifest)
        except Exception as e:
            self.error.emit(str(e))


class ExportPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._changeset: ChangeSet | None = None
        self._selected_files: set = set()
        self._selected_reg: set = set()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("<h2>Export Package</h2>"))

        # Output dir picker
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Output directory:"))
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("Choose output folder…")
        dir_row.addWidget(self._dir_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        self._summary_label = QLabel("")
        layout.addWidget(self._summary_label)

        self._export_btn = QPushButton("Export")
        self._export_btn.setFixedHeight(36)
        self._export_btn.clicked.connect(self._do_export)
        layout.addWidget(self._export_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        layout.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(150)
        self._log.hide()
        layout.addWidget(self._log)

        self._open_btn = QPushButton("Open Output Folder")
        self._open_btn.hide()
        self._open_btn.clicked.connect(self._open_folder)
        layout.addWidget(self._open_btn)

        layout.addStretch()

    def configure(self, changeset: ChangeSet, selected_files: set, selected_reg: set):
        self._changeset = changeset
        self._selected_files = selected_files
        self._selected_reg = selected_reg
        self._summary_label.setText(
            f"{len(selected_files):,} files  +  {len(selected_reg):,} registry values selected for export"
        )
        self._log.clear()
        self._log.hide()
        self._open_btn.hide()
        self._progress.hide()
        self._export_btn.setEnabled(True)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self._dir_edit.setText(path)

    def get_output_dir(self) -> str:
        return self._dir_edit.text().strip()

    def set_output_dir(self, path: str):
        if path:
            self._dir_edit.setText(path)

    def _do_export(self):
        out_dir = self._dir_edit.text().strip()
        if not out_dir:
            self._log.show()
            self._log.append("Please choose an output directory first.")
            return

        self._export_btn.setEnabled(False)
        self._progress.show()
        self._log.show()
        self._log.clear()
        self._log.append(f"Exporting to: {out_dir}")

        self._worker = _ExportWorker(
            self._changeset,
            self._selected_files,
            self._selected_reg,
            out_dir,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def _on_done(self, manifest: dict):
        self._progress.hide()
        file_count = len(manifest.get("files", {}))
        reg_count = len(manifest.get("registry", {}))
        self._log.append(f"\nDone! Exported {file_count} files and {reg_count} registry values.")
        self._log.append(f"Output: {self._dir_edit.text()}")
        self._open_btn.show()

    def _on_error(self, msg: str):
        self._progress.hide()
        self._export_btn.setEnabled(True)
        self._log.append(f"\nError: {msg}")

    def _open_folder(self):
        import subprocess
        path = self._dir_edit.text().strip()
        if path and os.path.exists(path):
            subprocess.Popen(["explorer", path])
