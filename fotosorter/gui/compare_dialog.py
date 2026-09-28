"""Side-by-side viewer for an original photo and its compressed copy, so you
can judge whether the quality loss from "Compress folder..." is acceptable.
Both panes load at full native resolution (unlike the review grid, which
caps resolution since it juggles several images at once) - this dialog only
ever shows one pair, and judging compression artifacts benefits from seeing
the real detail."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from .. import compress, config, metadata
from .zoomable_image import ZoomableImageLabel


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MB"
    return f"{num_bytes / 1024:.0f} KB"


class CompareDialog(QDialog):
    def __init__(self, data_dir: Path, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.root: Path | None = None
        self.pairs: list[tuple[Path, Path]] = []

        self.setWindowTitle("Compare original / compressed")
        self.resize(1300, 850)

        layout = QVBoxLayout(self)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(str(data_dir))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load)
        folder_row.addWidget(QLabel("Folder:"))
        folder_row.addWidget(self.folder_edit, stretch=1)
        folder_row.addWidget(browse_btn)
        folder_row.addWidget(load_btn)
        layout.addLayout(folder_row)

        splitter = QSplitter(Qt.Horizontal)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._show_pair)
        splitter.addWidget(self.list_widget)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.stats_label = QLabel(
            'Pick a folder that has a "..._compressed" sibling somewhere under it '
            "(e.g. DATA/, or a specific SAVED folder) and click Load."
        )
        self.stats_label.setWordWrap(True)
        right_layout.addWidget(self.stats_label)

        images_row = QHBoxLayout()
        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("Original"))
        self._left_layout = QVBoxLayout()
        left_col.addLayout(self._left_layout, stretch=1)
        images_row.addLayout(left_col, stretch=1)

        right_col = QVBoxLayout()
        right_col.addWidget(QLabel("Compressed"))
        self._right_layout = QVBoxLayout()
        right_col.addLayout(self._right_layout, stretch=1)
        images_row.addLayout(right_col, stretch=1)

        right_layout.addLayout(images_row, stretch=1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, stretch=1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def _browse(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose folder", self.folder_edit.text())
        if chosen:
            self.folder_edit.setText(chosen)

    def _load(self):
        root = Path(self.folder_edit.text())
        if not root.is_dir():
            QMessageBox.warning(self, "Invalid folder", "That folder doesn't exist.")
            return

        self.root = root
        self.pairs = compress.find_compressed_pairs(root, config.SUPPORTED_EXTENSIONS)
        self.list_widget.clear()
        for orig, _ in self.pairs:
            self.list_widget.addItem(str(orig.relative_to(root)))

        if not self.pairs:
            self.stats_label.setText(
                f"No original/compressed pairs found under {root}. "
                'Photos need a "..._compressed" sibling folder - run "Compress folder..." first.'
            )
        else:
            self.stats_label.setText(f"Found {len(self.pairs)} pair(s). Select one on the left.")
            self.list_widget.setCurrentRow(0)

    def _clear_pane(self, layout: QVBoxLayout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_pair(self, row: int):
        if row < 0 or row >= len(self.pairs):
            return
        orig_path, comp_path = self.pairs[row]

        self._clear_pane(self._left_layout)
        self._clear_pane(self._right_layout)

        max_zoom = self.settings["zoom_max_level"]
        orig_img = metadata.load_normalized(orig_path)
        comp_img = metadata.load_normalized(comp_path)
        self._left_layout.addWidget(ZoomableImageLabel(orig_img, max_zoom))
        self._right_layout.addWidget(ZoomableImageLabel(comp_img, max_zoom))

        orig_size = orig_path.stat().st_size
        comp_size = comp_path.stat().st_size
        pct_smaller = (1 - comp_size / orig_size) * 100 if orig_size else 0
        self.stats_label.setText(
            f"Original: {orig_path.name} - {orig_img.width}x{orig_img.height}, {_format_size(orig_size)}"
            f"     |     Compressed: {comp_path.name} - {comp_img.width}x{comp_img.height}, "
            f"{_format_size(comp_size)} ({pct_smaller:.0f}% smaller)"
        )
