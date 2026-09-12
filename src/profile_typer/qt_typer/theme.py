"""Shared typography, colors, and application assets."""
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette

ASSETS = Path(__file__).resolve().parents[1] / "assets"
INK = "#20231f"
PAPER = "#f4f2e9"
ACCENT = "#d9f266"
MUTED = "#62665c"


def app_icon():
    return QIcon(str(ASSETS / "profile-typer.png"))


def mono_font(size=9):
    return QFont("Space Mono", size)


def configure_application(app):
    if not app.property("typerFontsLoaded"):
        for name in ("SpaceGrotesk.ttf", "SpaceMono.ttf"):
            QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / name))
        app.setProperty("typerFontsLoaded", True)
    app.setStyle("Fusion")
    app.setFont(QFont("Space Grotesk", 10))
    app.setWindowIcon(app_icon())
    palette = app.palette()
    for role, color in ((QPalette.ColorRole.Window, PAPER), (QPalette.ColorRole.Base, "#fffef9"),
                        (QPalette.ColorRole.WindowText, INK), (QPalette.ColorRole.Text, INK),
                        (QPalette.ColorRole.Button, PAPER), (QPalette.ColorRole.ButtonText, INK),
                        (QPalette.ColorRole.PlaceholderText, MUTED), (QPalette.ColorRole.Highlight, ACCENT),
                        (QPalette.ColorRole.HighlightedText, INK)):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#7b7e73"))
    app.setPalette(palette)
    app.setStyleSheet((ASSETS / "theme.qss").read_text(encoding="utf-8").replace("@assets", ASSETS.as_posix()))
