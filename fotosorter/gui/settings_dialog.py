"""Dialog to tune the quality/similarity heuristics without hand-editing JSON."""
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QSpinBox

from .. import config

_FIELDS = [
    ("time_window_seconds", "Burst time window (seconds)", QSpinBox, 1, 3600),
    ("phash_hamming_threshold", "Similarity threshold (0=identical, 64=unrelated)", QSpinBox, 0, 64),
    ("max_group_size", "Max photos per review group before splitting", QSpinBox, 2, 200),
    ("max_grid_columns", "Max columns in the review grid", QSpinBox, 1, 8),
    ("sharpness_threshold", "Blur threshold (lower = stricter)", QDoubleSpinBox, 0, 10000),
    ("exposure_dark_mean_threshold", "Underexposed if mean brightness below", QDoubleSpinBox, 0, 255),
    ("exposure_bright_mean_threshold", "Overexposed if mean brightness above", QDoubleSpinBox, 0, 255),
    ("exposure_clip_fraction_threshold", "Bad exposure if clipped-pixel fraction above", QDoubleSpinBox, 0, 1),
    ("zoom_source_max_dim", "Max zoom source resolution (px, longest edge)", QSpinBox, 200, 10000),
    ("zoom_max_level", "Max zoom-in steps per photo", QSpinBox, 1, 12),
    ("compress_target_kb", "Compression target size (KB)", QSpinBox, 50, 20000),
    ("compress_min_quality", "Compression minimum JPEG quality", QSpinBox, 1, 95),
    ("compress_min_dim", "Compression minimum resolution (px, longest edge)", QSpinBox, 200, 10000),
    ("compress_allow_downscale", "Allow shrinking resolution to hit the compression target", QCheckBox, None, None),
    ("compress_on_save", "Compress photos when saving (copies to a *_compressed folder, originals untouched)", QCheckBox, None, None),
]


class SettingsDialog(QDialog):
    def __init__(self, config_dir, current_settings: dict, parent=None):
        super().__init__(parent)
        self.config_dir = config_dir
        self.setWindowTitle("Settings")
        self._widgets = {}

        layout = QFormLayout(self)
        for key, label, widget_cls, lo, hi in _FIELDS:
            widget = widget_cls()
            if widget_cls is QCheckBox:
                widget.setChecked(bool(current_settings[key]))
            else:
                if isinstance(widget, QDoubleSpinBox):
                    widget.setDecimals(3)
                widget.setRange(lo, hi)
                widget.setValue(current_settings[key])
            self._widgets[key] = widget
            layout.addRow(label, widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        new_settings = {
            key: (widget.isChecked() if isinstance(widget, QCheckBox) else widget.value())
            for key, widget in self._widgets.items()
        }
        config.save_settings(self.config_dir, new_settings)
        self.result_settings = new_settings
        super().accept()
