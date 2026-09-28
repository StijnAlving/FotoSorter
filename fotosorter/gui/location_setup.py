"""Dialog for defining date-range -> location-name rules, used whenever a
photo's country can't be determined from GPS EXIF."""
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

from .. import config


def _to_qdate(iso: str) -> QDate:
    return QDate.fromString(iso, "yyyy-MM-dd")


class LocationSetupDialog(QDialog):
    def __init__(self, config_dir, hint_dates: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.config_dir = config_dir
        self.setWindowTitle("Trip locations")
        self.resize(480, 360)

        self.rules = config.load_location_rules(config_dir)

        layout = QVBoxLayout(self)

        if hint_dates:
            layout.addWidget(QLabel(
                f"{len(hint_dates)} photo(s) have no location rule covering their date "
                f"(earliest {min(hint_dates)[:10]}, latest {max(hint_dates)[:10]}).\n"
                "Add a rule below covering that range, e.g. label it \"USA\" or \"Netherlands\"."
            ))

        self.list_widget = QListWidget()
        self._refresh_list()
        layout.addWidget(self.list_widget)

        remove_btn = QPushButton("Remove selected rule")
        remove_btn.clicked.connect(self._remove_selected)
        layout.addWidget(remove_btn)

        form = QHBoxLayout()
        self.start_edit = QDateEdit(calendarPopup=True)
        self.end_edit = QDateEdit(calendarPopup=True)
        self.start_edit.setDate(QDate.currentDate())
        self.end_edit.setDate(QDate.currentDate())
        if hint_dates:
            self.start_edit.setDate(_to_qdate(min(hint_dates)[:10]))
            self.end_edit.setDate(_to_qdate(max(hint_dates)[:10]))
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Location name, e.g. USA")
        add_btn = QPushButton("Add rule")
        add_btn.clicked.connect(self._add_rule)
        form.addWidget(QLabel("From:"))
        form.addWidget(self.start_edit)
        form.addWidget(QLabel("To:"))
        form.addWidget(self.end_edit)
        form.addWidget(self.label_edit)
        form.addWidget(add_btn)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_list(self):
        self.list_widget.clear()
        for rule in self.rules:
            item = QListWidgetItem(f"{rule['start']} → {rule['end']}: {rule['label']}")
            self.list_widget.addItem(item)

    def _add_rule(self):
        label = self.label_edit.text().strip()
        if not label:
            QMessageBox.warning(self, "Missing label", "Type a location name first.")
            return
        start = self.start_edit.date().toString("yyyy-MM-dd")
        end = self.end_edit.date().toString("yyyy-MM-dd")
        if date.fromisoformat(start) > date.fromisoformat(end):
            QMessageBox.warning(self, "Invalid range", "Start date must be before end date.")
            return
        self.rules.append({"start": start, "end": end, "label": label})
        self.label_edit.clear()
        self._refresh_list()

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            del self.rules[row]
            self._refresh_list()

    def accept(self):
        config.save_location_rules(self.config_dir, self.rules)
        super().accept()
