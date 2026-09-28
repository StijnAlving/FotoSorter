"""Displays one duplicate/burst group as an adaptive grid: every photo is
shown at once, each with a zoom viewer and a keep checkbox. Columns are
capped (max_grid_columns) so photos never get squeezed into unreasonably
narrow slices - once a group needs more rows than fit on screen, the grid
scrolls vertically instead of shrinking cells further. The photo with the
best sharpness score gets a yellow border - drawn on the image itself
rather than a separate label, so it doesn't shrink the displayed image."""
import math

from PIL import Image
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .. import metadata
from .zoomable_image import ZoomableImageLabel


def grid_shape(n: int, max_cols: int) -> tuple[int, int]:
    """Pick (rows, cols): as many columns as photos, up to max_cols, then
    wrap into further rows rather than adding more columns."""
    cols = max(1, min(n, max_cols))
    rows = math.ceil(n / cols)
    return rows, cols


class ImageCell(QWidget):
    def __init__(self, file_row, pil_image: Image.Image, is_sharpest: bool, max_zoom_level: int, parent=None):
        super().__init__(parent)
        self.file_id = file_row["id"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.viewer = ZoomableImageLabel(pil_image, max_zoom_level=max_zoom_level)
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if is_sharpest:
            self.viewer.setStyleSheet("background-color: black; border: 4px solid yellow;")
        layout.addWidget(self.viewer, stretch=1)

        self.checkbox = QCheckBox("Keep this one" + (" (sharpest suggestion)" if is_sharpest else ""))
        self.checkbox.setChecked(is_sharpest)
        layout.addWidget(self.checkbox)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()


class ReviewGrid(QWidget):
    """Shows one group; calls on_save(kept_ids: set[int]) when the user saves."""

    def __init__(self, file_rows: list, settings: dict, on_save, parent=None):
        super().__init__(parent)
        self._on_save = on_save
        self._cells: list[ImageCell] = []
        self._max_cols = settings["max_grid_columns"]
        self._grid_spacing = 6

        layout = QVBoxLayout(self)

        header = QLabel(f"{len(file_rows)} similar photos taken around {file_rows[0]['date_taken']}")
        header.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(self._grid_spacing)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.grid_container)
        layout.addWidget(self.scroll_area, stretch=1)

        save_btn = QPushButton("Save && Next")
        save_btn.clicked.connect(self._handle_save)
        layout.addWidget(save_btn)

        sharpest_id = max(file_rows, key=lambda r: r["sharpness"] or 0)["id"]
        aspects = []
        for row in file_rows:
            img = metadata.load_normalized(row["path"], max_dim=settings["zoom_source_max_dim"])
            cell = ImageCell(row, img, row["id"] == sharpest_id, settings["zoom_max_level"])
            self._cells.append(cell)
            aspects.append(img.width / img.height)

        self._photo_aspect = sum(aspects) / len(aspects)
        self._layout_cells()

    def _layout_cells(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            item.widget().setParent(None)

        n = len(self._cells)
        rows, cols = grid_shape(n, self._max_cols)

        viewport_w = max(self.scroll_area.viewport().width(), 200)
        cell_w = (viewport_w - self._grid_spacing * (cols - 1)) / cols
        cell_h = cell_w / self._photo_aspect

        for i, cell in enumerate(self._cells):
            cell.setFixedSize(round(cell_w), round(cell_h))
            self.grid_layout.addWidget(cell, i // cols, i % cols)
            cell.show()

        self.grid_container.setMinimumHeight(round(rows * cell_h + self._grid_spacing * max(rows - 1, 0)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_cells()

    def _handle_save(self):
        kept = {cell.file_id for cell in self._cells if cell.is_checked()}
        if not kept:
            reply = QMessageBox.question(
                self, "Discard all?",
                "No photos are checked - all of them will be discarded. Continue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._on_save(kept)
