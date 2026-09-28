"""App shell: runs the ingest pipeline in the background on launch, then
walks the user through any pending duplicate-group reviews. Every step that
can take a while (scanning, analyzing photos, saving a group - which can
now trigger compression - and resolving locations) runs off the main
thread and reports progress through the shared progress bar."""
from pathlib import Path

from PySide6.QtWidgets import (
    QLabel, QMainWindow, QMessageBox, QProgressBar, QToolBar, QVBoxLayout, QWidget,
)

from .. import config, db, ingest
from .compare_dialog import CompareDialog
from .compress_dialog import CompressDialog
from .location_setup import LocationSetupDialog
from .lowquality_browser import LowQualityBrowserDialog
from .review_grid import ReviewGrid
from .settings_dialog import SettingsDialog
from .workers import BackgroundWorker

_PHASE_LABELS = {
    "scan": "Scanning for new files",
    "analyze": "Analyzing photos (quality + similarity)",
    "auto_save": "Auto-saving photos with no duplicates",
    "locate": "Filing photos",
    "save": "Saving your choices",
    "recheck": "Re-checking lowQuality photos",
}


class MainWindow(QMainWindow):
    def __init__(self, raw_dirs: list[Path], data_dir: Path, config_dir: Path, db_path: Path):
        super().__init__()
        self.raw_dirs, self.data_dir, self.config_dir, self.db_path = raw_dirs, data_dir, config_dir, db_path
        self.settings = config.load_settings(config_dir)
        self.conn = None
        self.review_queue: list[int] = []
        self._busy = False

        self.setWindowTitle("FotoSorter")
        self.resize(1100, 800)

        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)
        rescan_action = self.toolbar.addAction("Re-scan RAW/")
        rescan_action.triggered.connect(self.run_sync)
        locations_action = self.toolbar.addAction("Location rules...")
        locations_action.triggered.connect(self.open_location_dialog)
        settings_action = self.toolbar.addAction("Settings...")
        settings_action.triggered.connect(self.open_settings_dialog)
        compress_action = self.toolbar.addAction("Compress folder...")
        compress_action.triggered.connect(self.open_compress_dialog)
        recheck_action = self.toolbar.addAction("Re-check lowQuality...")
        recheck_action.triggered.connect(self.run_recheck_low_quality)
        compare_action = self.toolbar.addAction("Compare original/compressed...")
        compare_action.triggered.connect(self.open_compare_dialog)
        browse_action = self.toolbar.addAction("Browse lowQuality...")
        browse_action.triggered.connect(self.open_lowquality_browser)

        self.status_label = QLabel("Starting...")
        self.compress_indicator = QLabel()
        self.compress_indicator.setStyleSheet("color: gray; font-style: italic;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        central = QWidget()
        self._central_layout = QVBoxLayout(central)
        self._central_layout.addWidget(self.status_label)
        self._central_layout.addWidget(self.compress_indicator)
        self._central_layout.addWidget(self.progress_bar)
        self.setCentralWidget(central)
        self._current_content: QWidget | None = None

        self._update_compress_indicator()
        self.run_sync()

    # -- background work ---------------------------------------------------

    def _run_background(self, work_fn, on_done):
        """Runs work_fn(progress_callback) off the main thread, showing the
        shared progress bar and disabling the toolbar until it's done."""
        if self._busy:
            return
        self._busy = True
        self.toolbar.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        def handle_done(result):
            self._busy = False
            self.toolbar.setEnabled(True)
            self.progress_bar.setVisible(False)
            on_done(result)

        def handle_failed(message):
            self._busy = False
            self.toolbar.setEnabled(True)
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "Error", message)
            self.status_label.setText("Something went wrong - see error dialog.")

        self._worker = BackgroundWorker(work_fn)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(handle_done)
        self._worker.failed.connect(handle_failed)
        self._worker.start()

    def _on_progress(self, phase: str, done: int, total: int):
        label = _PHASE_LABELS.get(phase, phase.capitalize())
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(done)
        self.status_label.setText(f"{label}... {done}/{total}")

    # -- pipeline ---------------------------------------------------------

    def run_sync(self):
        self._set_content(None)
        self.status_label.setText("Starting scan...")

        def work(progress):
            conn = db.connect(self.db_path)
            summary = ingest.sync(conn, self.raw_dirs, self.data_dir, self.config_dir, self.settings, progress)
            conn.close()
            return summary

        self._run_background(work, on_done=self._on_sync_done)

    def _on_sync_done(self, summary: dict):
        self.conn = db.connect(self.db_path)
        self.status_label.setText(
            f"Found {summary['new_files_found']} new file(s): "
            f"{summary['low_quality']} low quality, {summary['auto_saved']} auto-saved, "
            f"{summary['groups_created']} group(s) need review."
        )
        self._check_needs_location()

    def _check_needs_location(self):
        pending = db.get_needs_location(self.conn)
        if not pending:
            self._load_review_queue()
            return

        dates = [row["date_taken"] for row in pending]
        LocationSetupDialog(self.config_dir, hint_dates=dates, parent=self).exec()

        def work(progress):
            conn = db.connect(self.db_path)
            resolved = ingest.resolve_pending_locations(conn, self.data_dir, self.config_dir, self.settings, progress)
            conn.close()
            return resolved

        def done(resolved):
            self.status_label.setText(f"{resolved} file(s) filed after adding location rule(s).")
            self._load_review_queue()

        self._run_background(work, on_done=done)

    def _load_review_queue(self):
        self.review_queue = db.get_pending_review_groups(self.conn)
        self._show_next_group()

    def _show_next_group(self):
        if not self.review_queue:
            self._set_content(QLabel("All caught up - no duplicate groups waiting for review."))
            return
        group_id = self.review_queue.pop(0)
        members = db.get_group_members(self.conn, group_id)
        grid = ReviewGrid(members, self.settings, on_save=lambda kept: self._save_group(group_id, kept))
        grid.group_id = group_id
        self._set_content(grid)

    def _save_group(self, group_id: int, kept_ids: set[int]):
        self._set_content(None)
        self.status_label.setText("Saving...")

        def work(progress):
            conn = db.connect(self.db_path)
            summary = ingest.resolve_group_choice(conn, group_id, kept_ids, self.data_dir, self.config_dir, self.settings, progress)
            conn.close()
            return summary

        def done(summary):
            msg = f"Saved: {summary['kept']} kept, {summary['discarded']} discarded"
            msg += f", {summary['compressed']} compressed." if self.settings.get("compress_on_save") else " (compression off)."
            self.status_label.setText(msg)
            self._check_needs_location_then_next()

        self._run_background(work, on_done=done)

    def _check_needs_location_then_next(self):
        pending = db.get_needs_location(self.conn)
        if not pending:
            self._show_next_group()
            return

        dates = [row["date_taken"] for row in pending]
        LocationSetupDialog(self.config_dir, hint_dates=dates, parent=self).exec()

        def work(progress):
            conn = db.connect(self.db_path)
            ingest.resolve_pending_locations(conn, self.data_dir, self.config_dir, self.settings, progress)
            conn.close()

        self._run_background(work, on_done=lambda _: self._show_next_group())

    def run_recheck_low_quality(self):
        reply = QMessageBox.question(
            self, "Re-check lowQuality photos",
            "Re-evaluates every photo currently filed as lowQuality against the current "
            "blur/exposure settings. Anything that no longer qualifies moves out into the "
            "normal SAVED location (grouped with other recovered photos taken close "
            "together, or saved on its own if there's no duplicate). Nothing is deleted. "
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._set_content(None)
        self.status_label.setText("Re-checking lowQuality photos...")

        def work(progress):
            conn = db.connect(self.db_path)
            recheck_summary = ingest.recheck_low_quality(conn, self.settings, progress)
            grouped = ingest.run_grouping(conn, self.settings, self.data_dir, self.config_dir, progress)
            resolved = ingest.resolve_pending_locations(conn, self.data_dir, self.config_dir, self.settings, progress)
            conn.close()
            return {**recheck_summary, **grouped, "locations_resolved": resolved}

        def done(summary):
            self.status_label.setText(
                f"Re-checked {summary['checked']} lowQuality photo(s): {summary['recovered']} recovered "
                f"({summary['auto_saved']} saved automatically, {summary['groups_created']} group(s) need "
                f"review), {summary['still_flagged']} still flagged."
            )
            self.conn = db.connect(self.db_path)
            self._check_needs_location()

        self._run_background(work, on_done=done)

    # -- dialogs ------------------------------------------------------------

    def open_location_dialog(self):
        LocationSetupDialog(self.config_dir, parent=self).exec()

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.config_dir, self.settings, parent=self)
        if dialog.exec():
            self.settings = dialog.result_settings
            self._update_compress_indicator()

    def open_compress_dialog(self):
        CompressDialog(self.data_dir, self.settings, parent=self).exec()

    def open_compare_dialog(self):
        CompareDialog(self.data_dir, self.settings, parent=self).exec()

    def open_lowquality_browser(self):
        LowQualityBrowserDialog(self.db_path, self.data_dir, self.config_dir, self.settings, parent=self).exec()

    def _update_compress_indicator(self):
        state = "ON" if self.settings.get("compress_on_save") else "OFF"
        self.compress_indicator.setText(f"Compress on save: {state}")

    # -- lifecycle ------------------------------------------------------------

    def closeEvent(self, event):
        if self._busy and self._worker.isRunning():
            self.status_label.setText("Finishing up before closing...")
            self._worker.wait()
        super().closeEvent(event)

    # -- helpers ------------------------------------------------------------

    def _set_content(self, widget: QWidget | None):
        if self._current_content is not None:
            self._central_layout.removeWidget(self._current_content)
            self._current_content.deleteLater()
            self._current_content = None
        if widget is not None:
            self._central_layout.addWidget(widget, stretch=1)
            self._current_content = widget
