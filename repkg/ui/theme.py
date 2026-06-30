"""Application theming — dark and light Fusion palettes with toggle."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

DARK = "dark"
LIGHT = "light"


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(50, 50, 50))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(42, 42, 42))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(130, 130, 130))
    return p


def _light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(245, 245, 245))
    p.setColor(QPalette.ColorRole.WindowText, QColor(20, 20, 20))
    p.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(235, 235, 235))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(20, 20, 20))
    p.setColor(QPalette.ColorRole.Text, QColor(20, 20, 20))
    p.setColor(QPalette.ColorRole.Button, QColor(230, 230, 230))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(20, 20, 20))
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link, QColor(20, 100, 200))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(140, 140, 140))
    return p


def apply_theme(app, theme: str):
    app.setStyle("Fusion")
    app.setPalette(_dark_palette() if theme == DARK else _light_palette())
