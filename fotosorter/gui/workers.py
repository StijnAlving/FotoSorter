"""Generic background-thread runner with progress reporting, shared by every
potentially-slow operation: scanning/analyzing photos, saving a reviewed
group, resolving pending locations, and batch compression."""
from PySide6.QtCore import QThread, Signal


class BackgroundWorker(QThread):
    progress = Signal(str, int, int)  # phase label, done, total
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            result = self._fn(lambda phase, done, total: self.progress.emit(phase, done, total))
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
