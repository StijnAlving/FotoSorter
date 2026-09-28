"""Manual, one-at-a-time triage tool for the lowQuality folder: scroll
through flagged photos and promote individual ones straight to SAVED,
independent of the threshold-based "Re-check lowQuality..." bulk tool.
Useful for the odd photo the automatic heuristics still get wrong without
having to retune thresholds for everyone else."""
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from .. import db, ingest, metadata
from .workers import BackgroundWorker
from .zoomable_image import ZoomableImageLabel


class LowQualityBrowserDialog(QDialog):
    def __init__(self, db_path: Path, data_dir: Path, config_dir: Path, settings: dict, parent=None):
        super().__init__(parent)
        self.db_path, self.data_dir, self.config_dir = db_path, data_dir, config_dir
        self.settings = settings
        self._rows: list[dict] = []
        self._index = 0
        self._busy = False
        self._worker = None

        self.setWindowTitle("Browse lowQuality")
        self.resize(1100, 800)

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.compress_checkbox = QCheckBox("Compress when moving to SAVED")
        self.compress_checkbox.setChecked(bool(settings.get("compress_on_save")))
        top_row.addWidget(self.compress_checkbox)
        top_row.addStretch(1)
        self.counter_label = QLabel("")
        top_row.addWidget(self.counter_label)
        layout.addLayout(top_row)

        self._viewer_container = QWidget()
        self._viewer_layout = QVBoxLayout(self._viewer_container)
        self._viewer_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._viewer_container, stretch=1)
        self._viewer = None

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton("<< Previous")
        self.prev_btn.clicked.connect(self._show_prev)
        self.move_btn = QPushButton("Move to SAVED")
        self.move_btn.clicked.connect(self._move_current)
        self.next_btn = QPushButton("Skip / Next >>")
        self.next_btn.clicked.connect(self._show_next)
        nav_row.addWidget(self.prev_btn)
        nav_row.addWidget(self.move_btn)
        nav_row.addWidget(self.next_btn)
        layout.addLayout(nav_row)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self._load_rows()
        self._show_current()

    def _load_rows(self):
        conn = db.connect(self.db_path)
        self._rows = [
            dict(r) for r in conn.execute(
                "SELECT * FROM files WHERE quality_flag = 'low_quality' AND status = 'done' ORDER BY date_taken"
            ).fetchall()
        ]
        conn.close()
        self._index = min(self._index, max(0, len(self._rows) - 1))

    def _clear_viewer(self):
        if self._viewer is not None:
            self._viewer_layout.removeWidget(self._viewer)
            self._viewer.deleteLater()
            self._viewer = None

    def _show_current(self):
        self._clear_viewer()
        has_rows = bool(self._rows)
        self.prev_btn.setEnabled(has_rows and self._index > 0)
        self.next_btn.setEnabled(has_rows and self._index < len(self._rows) - 1)
        self.move_btn.setEnabled(has_rows)

        if not has_rows:
            self.counter_label.setText("0 of 0")
            self.info_label.setText("No lowQuality photos left.")
            return

        row = self._rows[self._index]
        img = metadata.load_normalized(Path(row["path"]))
        self._viewer = ZoomableImageLabel(img, self.settings["zoom_max_level"])
        self._viewer_layout.addWidget(self._viewer)

        self.counter_label.setText(f"{self._index + 1} of {len(self._rows)}")
        reasons = json.loads(row["quality_reasons"]) if row["quality_reasons"] else []
        self.info_label.setText(f"{Path(row['path']).name} - flagged for: {', '.join(reasons) or 'unknown'}")

    def _show_next(self):
        if self._index < len(self._rows) - 1:
            self._index += 1
            self._show_current()

    def _show_prev(self):
        if self._index > 0:
            self._index -= 1
            self._show_current()

    def _move_current(self):
        if not self._rows or self._busy:
            return
        row = self._rows[self._index]
        compress_now = self.compress_checkbox.isChecked()

        self._busy = True
        self.prev_btn.setEnabled(False)
        self.move_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.info_label.setText("Moving...")

        def work(_progress):
            conn = db.connect(self.db_path)
            db_row = conn.execute("SELECT * FROM files WHERE id = ?", (row["id"],)).fetchone()
            effective_settings = dict(self.settings)
            effective_settings["compress_on_save"] = compress_now
            result = ingest.finalize_file(conn, db_row, self.data_dir, self.config_dir, kept=True, settings=effective_settings)
            conn.close()
            return result

        def done(result):
            self._busy = False
            self.progress_bar.setVisible(False)
            if result["filed"]:
                del self._rows[self._index]
                if self._index >= len(self._rows):
                    self._index = max(0, len(self._rows) - 1)
                msg = "Moved to SAVED" + (" and compressed." if result["compressed"] else " (compression off).")
            else:
                msg = "Couldn't file it - no location rule covers this photo's date yet. Use \"Location rules...\", then try again."
            self._show_current()
            self.info_label.setText(f"{msg}  |  {self.info_label.text()}")

        def failed(message):
            self._busy = False
            self.progress_bar.setVisible(False)
            self.prev_btn.setEnabled(self._index > 0)
            self.next_btn.setEnabled(self._index < len(self._rows) - 1)
            self.move_btn.setEnabled(True)
            QMessageBox.critical(self, "Error", message)

        self._worker = BackgroundWorker(work)
        self._worker.finished_ok.connect(done)
        self._worker.failed.connect(failed)
        self._worker.start()

    def closeEvent(self, event):
        if self._busy and self._worker is not None and self._worker.isRunning():
            self.info_label.setText("Finishing current move before closing...")
            self._worker.wait()
        super().closeEvent(event)
