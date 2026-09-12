"""Render the vector masters into app, taskbar, and control icons."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication
from PIL import Image


def main():
    app = QApplication.instance() or QApplication([])
    assets = Path(__file__).resolve().parents[1] / "src/profile_typer/assets"
    for name, size in (("profile-typer", 256), ("chevron-down", 32), ("chevron-up", 32),
                       ("clipboard", 64), ("pencil", 64), ("pencil-light", 64)):
        renderer = QSvgRenderer(str(assets / f"{name}.svg"))
        output = QImage(size, size, QImage.Format.Format_ARGB32)
        output.fill(Qt.GlobalColor.transparent)
        painter = QPainter(output)
        renderer.render(painter)
        painter.end()
        assert output.save(str(assets / f"{name}.png"))
    Image.open(assets / "profile-typer.png").save(assets / "profile-typer.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    app.quit()


if __name__ == "__main__":
    main()
