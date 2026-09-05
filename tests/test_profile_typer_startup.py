"""Exercise the real launcher with a window initially outside every display."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
except ImportError as error:
    raise unittest.SkipTest("Install requirements-typer.txt to run Qt startup tests") from error

from profile_typer.profile_typer_gui import main
from profile_typer.qt_typer.window import TyperWindow
from profile_typer.typing_backends import PreviewTypingBackend


class TyperStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_launcher_moves_offscreen_window_into_connected_display(self):
        window = TyperWindow(backend=PreviewTypingBackend())
        window.setGeometry(QRect(5000, -200, 1000, 720))
        try:
            with patch("profile_typer.qt_typer.window.TyperWindow", return_value=window), patch.object(QApplication, "exec", return_value=0):
                self.assertEqual(main(["--dry-run", "--no-settings"]), 0)
            self.app.processEvents()
            self.assertTrue(window.isVisible())
            self.assertFalse(window.isMinimized())
            self.assertTrue(any(screen.availableGeometry().contains(window.frameGeometry()) for screen in self.app.screens()),
                            f"Window outside desktop: {window.frameGeometry()}")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()
