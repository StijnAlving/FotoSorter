"""A QLabel that shows a photo and supports click-to-zoom: left click zooms
in centered on the click point, right click zooms out one step. Zooming
crops the source image rather than upscaling the widget, so detail stays
sharp enough to judge focus."""
from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


class ZoomableImageLabel(QLabel):
    def __init__(self, pil_image: Image.Image, max_zoom_level: int = 6, parent=None):
        super().__init__(parent)
        self._image = pil_image
        self._full_w, self._full_h = pil_image.size
        self._max_zoom = max_zoom_level
        self._zoom_level = 0
        self._center = (self._full_w / 2, self._full_h / 2)
        # (offset_x, offset_y, disp_w, disp_h) of the pixmap within this
        # widget, and the crop box it was rendered from - needed to map a
        # click back to source-image coordinates.
        self._display_rect = (0, 0, 0, 0)
        self._crop_box = (0, 0, self._full_w, self._full_h)

        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(80, 60)
        self.setStyleSheet("background-color: black;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._zoom_level < self._max_zoom:
            self._zoom_in_at(event.position().toPoint())
        elif event.button() == Qt.RightButton and self._zoom_level > 0:
            self._zoom_level -= 1
            self._render()

    def _zoom_in_at(self, click_pos: QPoint):
        off_x, off_y, disp_w, disp_h = self._display_rect
        if disp_w <= 0 or disp_h <= 0:
            return
        # Ignore clicks that land in the letterboxed margin, not the image.
        if not (off_x <= click_pos.x() <= off_x + disp_w and off_y <= click_pos.y() <= off_y + disp_h):
            return
        frac_x = (click_pos.x() - off_x) / disp_w
        frac_y = (click_pos.y() - off_y) / disp_h
        cx0, cy0, cx1, cy1 = self._crop_box
        self._center = (cx0 + frac_x * (cx1 - cx0), cy0 + frac_y * (cy1 - cy0))
        self._zoom_level += 1
        self._render()

    def _render(self):
        w, h = max(self.width(), 1), max(self.height(), 1)
        factor = 2 ** self._zoom_level
        crop_w = self._full_w / factor
        crop_h = self._full_h / factor
        cx, cy = self._center
        x0 = min(max(cx - crop_w / 2, 0), self._full_w - crop_w)
        y0 = min(max(cy - crop_h / 2, 0), self._full_h - crop_h)
        self._crop_box = (x0, y0, x0 + crop_w, y0 + crop_h)

        cropped = self._image.crop((round(x0), round(y0), round(x0 + crop_w), round(y0 + crop_h)))
        qimage = ImageQt(cropped)
        pixmap = QPixmap.fromImage(qimage).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)

        off_x = (w - pixmap.width()) / 2
        off_y = (h - pixmap.height()) / 2
        self._display_rect = (off_x, off_y, pixmap.width(), pixmap.height())

    def reset_zoom(self):
        self._zoom_level = 0
        self._center = (self._full_w / 2, self._full_h / 2)
        self._render()
