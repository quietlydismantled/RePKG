import sys

from PySide6.QtWidgets import QApplication

from repkg.ui.main_window import MainWindow
from repkg.ui.theme import DARK, apply_theme


def main():
    app = QApplication(sys.argv)
    apply_theme(app, DARK)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
