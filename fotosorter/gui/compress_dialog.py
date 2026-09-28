"""Batch 'Compress folder' tool: walks a folder and writes a smaller copy of
each photo into a sibling '..._compressed' folder. Originals are never
modified, moved, or deleted by this dialog."""
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QDialog,
)

from .. import compress
from .workers import BackgroundWorker


class CompressDialog(QDialog):
    def __init__(self, data_dir: Path, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._worker = None
        self.setWindowTitle("Compress folder")
        self.resize(520, 260)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Writes a smaller copy of each photo into a sibling \"..._compressed\" "
            "folder next to SAVED/DISCARDED. Originals are never changed, moved, or deleted."
        ))

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(str(data_dir))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        folder_row.addWidget(QLabel("Folder:"))
        folder_row.addWidget(self.folder_edit, stretch=1)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        target_row = QHBoxLayout()
        self.target_spin = QSpinBox()
        self.target_spin.setRange(50, 20000)
        self.target_spin.setValue(settings["compress_target_kb"])
        self.target_spin.setSuffix(" KB")
        target_row.addWidget(QLabel("Target size:"))
        target_row.addWidget(self.target_spin)
        layout.addLayout(target_row)

        self.downscale_check = QCheckBox("Allow shrinking resolution to hit the target")
        self.downscale_check.setChecked(settings["compress_allow_downscale"])
        layout.addWidget(self.downscale_check)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self._start)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_row.addStretch(1)
        button_row.addWidget(self.start_btn)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

    def _browse(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose folder", self.folder_edit.text())
        if chosen:
            self.folder_edit.setText(chosen)

    def _start(self):
        folder = Path(self.folder_edit.text())
        if not folder.is_dir():
            QMessageBox.warning(self, "Invalid folder", "That folder doesn't exist.")
            return

        self.start_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Scanning folder...")

        target_bytes = self.target_spin.value() * 1024
        allow_downscale = self.downscale_check.isChecked()
        settings = self.settings

        def work(progress):
            return compress.compress_folder(folder, target_bytes, allow_downscale, settings, progress)

        self._worker = BackgroundWorker(work)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, phase: str, done: int, total: int):
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(done)
        self.status_label.setText(f"Compressing... {done}/{total}")

    def _on_done(self, summary: dict):
        compressed_mb = summary["new_bytes"] / (1024 * 1024)
        original_mb = summary["original_bytes"] / (1024 * 1024)
        self.status_label.setText(
            f"Done: {summary['compressed']} compressed, {summary['copied']} already small (copied as-is), "
            f"{summary['already_done']} already had a compressed copy, {summary['errors']} error(s). "
            f"The *_compressed folder(s) total ~{compressed_mb:.0f} MB, versus ~{original_mb:.0f} MB for the "
            f"same photos at original size - originals are untouched and still take their full space too."
        )
        self.start_btn.setEnabled(True)

    def _on_failed(self, message: str):
        QMessageBox.critical(self, "Error", f"Compression failed:\n{message}")
        self.start_btn.setEnabled(True)

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("Finishing current file before closing...")
            self._worker.wait()
        super().closeEvent(event)
