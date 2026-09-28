"""FotoSorter entry point.

Run with: .venv/bin/python main.py
"""
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from fotosorter.gui.main_window import MainWindow

PROJECT_ROOT = Path(__file__).resolve().parent


def main():
    app = QApplication(sys.argv)

    raw_dirs = [PROJECT_ROOT / "RAW"]
    data_dir = PROJECT_ROOT / "DATA"
    config_dir = PROJECT_ROOT / "config"
    db_path = PROJECT_ROOT / "fotosorter.db"

    window = MainWindow(raw_dirs, data_dir, config_dir, db_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
