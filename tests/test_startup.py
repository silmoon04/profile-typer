import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QObject
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from profile_typer.qt_typer.placement import show_on_screen
from profile_typer.qt_typer.window import TyperWindow, configure_application
from profile_typer.typing_backends import PreviewTypingBackend


def test_launch_load_navigation_and_resize_show_only_the_main_window():
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    shown = []

    class WatchWindows(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
                shown.append((type(watched).__name__, watched.objectName()))
            return False

    watcher = WatchWindows()
    app.installEventFilter(watcher)
    window = TyperWindow(backend=PreviewTypingBackend())
    try:
        show_on_screen(window)
        window.open_json(path=Path(__file__).parents[1] / "src/profile_typer/examples/views.json")
        for offset in (1, 1, -1, -1):
            window.navigate(offset)
        for width, height in ((380, 500), (1100, 900), (500, 650)):
            window.resize(width, height)
            app.processEvents()
            QTest.qWait(10)
        assert shown == [("TyperWindow", "")], f"Unexpected top-level windows: {shown}"
    finally:
        app.removeEventFilter(watcher)
        window.document.dirty = False
        window.close()
        window.deleteLater()
        app.processEvents()
