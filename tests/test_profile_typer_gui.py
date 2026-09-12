"""Qt interaction tests run offscreen by default and never inject OS input."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox
except ImportError as error:
    raise unittest.SkipTest("Install requirements-typer.txt to run Qt tests") from error

from profile_typer.qt_typer.model import QueueModel
from profile_typer.qt_typer.dialogs import PasteJsonDialog
from profile_typer.qt_typer.window import TyperWindow, configure_application
from profile_typer.typing_backends import PreviewTypingBackend
from profile_typer.typing_document import TypingDocument
from profile_typer.typing_queue import TypingItem, dump_queue, load_queue
from profile_typer.typing_session import Phase


class ProfileTyperGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        configure_application(cls.app)

    def setUp(self):
        self.backend = PreviewTypingBackend(speedup=50)
        self.window = TyperWindow(backend=self.backend)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.session.stop()
        self.wait_idle()
        self.window.document.dirty = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def edit(self, title="hello", description="text to type out\n\n"):
        self.window.title_edit.setText(title)
        self.window.description_edit.setPlainText(description)
        self.app.processEvents()

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while self.window.session.busy and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.assertFalse(self.window.session.busy)

    def assert_visible_inside(self, widget):
        self.assertTrue(widget.isVisible(), widget.objectName() or type(widget).__name__)
        position = widget.mapTo(self.window, QPoint(0, 0))
        self.assertGreaterEqual(position.x(), 0)
        self.assertGreaterEqual(position.y(), 0)
        self.assertLessEqual(position.x() + widget.width(), self.window.width())
        self.assertLessEqual(position.y() + widget.height(), self.window.height())

    def test_small_and_snapped_windows_keep_editor_and_actions_visible(self):
        for width, height in ((380, 420), (640, 480), (960, 540), (1080, 780), (360, 400)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                self.app.processEvents()
                QTest.qWait(50)
                self.assertEqual((self.window.width(), self.window.height()), (width, height))
                for widget in (self.window.description_edit, self.window.start_button, self.window.stop_button,
                               self.window.target_combo, self.window.back_button, self.window.next_button,
                               self.window.paste_button, *self.window.spins.values()):
                    self.assert_visible_inside(widget)
                self.assertGreaterEqual(self.window.description_edit.height(), 70)

    def test_paste_button_imports_json_without_file_dialog(self):
        def fill_dialog():
            dialog = self.app.activeModalWidget()
            self.assertIsInstance(dialog, PasteJsonDialog)
            dialog.editor.setPlainText('[{"title":"pasted title","description":"pasted text\\n\\n"}]')
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)

        QTimer.singleShot(0, fill_dialog)
        QTest.mouseClick(self.window.paste_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.document.selected.title, "pasted title")
        self.assertEqual(self.window.description_edit.toPlainText(), "pasted text\n\n")
        self.assertTrue(self.window.document.dirty)
        self.assertIsNone(self.window.document.path)

    def test_paste_append_preserves_current_edits(self):
        self.edit("existing", "keep this")

        def fill_dialog():
            dialog = self.app.activeModalWidget()
            dialog.editor.setPlainText('{"title":"next","description":"new text"}')
            dialog.mode.setCurrentIndex(1)
            dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()

        QTimer.singleShot(0, fill_dialog)
        self.window.paste_json()
        self.assertEqual(len(self.window.document.entries), 2)
        self.assertEqual(self.window.document.entries[0].description, "keep this")
        self.assertEqual(self.window.document.selected.title, "next")

    def test_invalid_paste_stays_open_and_keeps_the_draft(self):
        dialog = PasteJsonDialog(self.window)
        dialog.show()
        dialog.editor.setPlainText('{"title":')
        dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        self.assertTrue(dialog.isVisible())
        self.assertIn("line", dialog.error_label.text())
        self.assertEqual(dialog.editor.toPlainText(), '{"title":')
        dialog.reject()
        dialog.deleteLater()

    def test_cancel_paste_does_not_modify_document(self):
        before = self.window.document.entries
        with patch.object(PasteJsonDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.window.paste_json()
        self.assertEqual(self.window.document.entries, before)

    def test_main_page_settings_control_the_actual_run(self):
        self.edit("hello", "text")
        self.window.tabs.setCurrentIndex(0)
        self.window.spins["wpm"].setValue(73.5)
        self.window.spins["corrections"].setValue(0.25)
        self.window.spins["variation"].setValue(80)
        self.window.spins["delay"].setValue(0)
        with patch.object(self.backend, "type", wraps=self.backend.type) as deliver:
            self.window.start_typing()
            self.wait_idle()
        settings = deliver.call_args.args[2]
        self.assertEqual((settings.wpm, settings.corrections, settings.variation, settings.delay), (73.5, 0.25, 80, 0))

    def test_edit_and_undo_use_document_without_resetting_editor_cursor(self):
        self.window.description_edit.setFocus()
        QTest.keyClicks(self.window.description_edit, "hello")
        self.assertEqual(self.window.document.selected.description, "hello")

        QTest.keyClick(self.window.description_edit, Qt.Key.Key_Left)
        QTest.keyClicks(self.window.description_edit, "!")
        self.assertEqual(self.window.document.selected.description, "hell!o")
        self.window.description_edit.undo()
        self.assertEqual(self.window.document.selected.description, "hello")

    def test_offscreen_renderer_has_real_font_glyphs(self):
        self.assertTrue(self.window.fontMetrics().inFont("A"))

    def test_navigation_and_reordering_preserve_unicode_and_trailing_newlines(self):
        self.edit("first", "café 👋\n\n")
        self.window.add_item()
        self.edit("second", "other")
        QTest.mouseClick(self.window.back_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.description_edit.toPlainText(), "café 👋\n\n")
        self.window.move_item(1)
        self.assertEqual(self.window.document.selected_index, 1)
        self.assertEqual(self.window.title_edit.text(), "first")
        self.window.add_item(duplicate=True)
        self.assertEqual(self.window.document.selected.description, "café 👋\n\n")

    def test_search_selects_by_identity_instead_of_filtered_position(self):
        self.edit("alpha", "first")
        self.window.add_item()
        self.edit("beta", "second")
        self.window.add_item()
        self.edit("gamma", "third")
        self.window.search.setText("beta")
        self.assertEqual(self.window.proxy.rowCount(), 1)
        index = self.window.proxy.index(0, 0)
        self.window.list_view.setCurrentIndex(index)
        self.app.processEvents()
        self.assertEqual(self.window.document.selected.title, "beta")
        self.assertEqual(self.window.description_edit.toPlainText(), "second")
        self.assertEqual(index.data(QueueModel.IdentityRole), self.window.document.selected_id)

    def test_empty_filter_does_not_lose_selection_or_edits(self):
        self.edit()
        identity = self.window.document.selected_id
        self.window.search.setText("no match")
        self.assertEqual(self.window.proxy.rowCount(), 0)
        self.assertEqual(self.window.document.selected_id, identity)
        self.assertEqual(self.window.description_edit.toPlainText(), "text to type out\n\n")
        self.window.search.clear()
        self.assertEqual(self.window.list_view.currentIndex().data(QueueModel.IdentityRole), identity)

    def test_resizing_and_tabs_preserve_editor_and_numeric_settings(self):
        self.edit()
        self.window.resize(380, 420)
        self.app.processEvents()
        self.window.tabs.setCurrentIndex(1)
        self.assertTrue(self.window.list_view.isVisible())
        self.window.tabs.setCurrentIndex(2)
        self.window.spins["wpm"].setValue(73.5)
        self.window.resize(960, 540)
        self.app.processEvents()
        self.assertEqual(self.window.tabs.currentIndex(), 2)
        self.window.tabs.setCurrentIndex(0)
        self.assertTrue(self.window.list_view.isVisible())
        self.assertEqual(self.window.description_edit.toPlainText(), "text to type out\n\n")
        self.assertEqual(self.window.spins["wpm"].value(), 73.5)
        self.assertTrue(self.window.document.dirty)

    def test_settings_scroll_in_short_window_with_footer_visible(self):
        self.window.resize(360, 400)
        self.window.tabs.setCurrentIndex(2)
        self.app.processEvents()
        scrollbar = self.window.settings_page.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        scrollbar.setValue(scrollbar.maximum())
        self.app.processEvents()
        self.assert_visible_inside(self.window.start_button)
        self.assert_visible_inside(self.window.stop_button)

    def test_preview_completes_description_only_and_advances_once(self):
        self.edit("title not typed", "exact\n\n")
        self.window.add_item()
        self.edit("next", "later")
        self.window.navigate(-1)
        self.window.spins["delay"].setValue(0)
        QTest.mouseClick(self.window.start_button, Qt.MouseButton.LeftButton)
        self.assertFalse(self.window.description_edit.isEnabled())
        self.wait_idle()
        self.assertEqual(self.backend.output, "exact\n\n")
        self.assertEqual(self.window.document.selected_index, 1)
        self.assertEqual(self.window.session.phase, Phase.DONE)
        self.assertEqual(self.window.progress.value(), 1000)

    def test_escape_cancels_countdown_without_output(self):
        self.edit()
        self.window.start_typing()
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertEqual(self.window.session.phase, Phase.STOPPED)
        self.assertEqual(self.backend.output, "")

    def test_close_during_typing_waits_and_stops_worker(self):
        self.edit("hello", "x" * 1000)
        self.window.spins["delay"].setValue(0)
        self.window.start_typing()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
            self.window.close()
            self.wait_idle()
            self.app.processEvents()
        self.assertFalse(self.window.session.busy)
        self.assertFalse(self.window.isVisible())

    def test_window_refresh_preserves_exact_handle(self):
        targets = [SimpleNamespace(hwnd=42, pid=100, title="Editor"), SimpleNamespace(hwnd=99, pid=100, title="Other")]
        with patch.object(self.backend, "targets", return_value=targets):
            self.window.refresh_windows()
            self.window.target_combo.setCurrentIndex(1)
        with patch.object(self.backend, "targets", return_value=list(reversed(targets))):
            self.window.refresh_windows()
        self.assertEqual(self.window.target_combo.currentData(), 42)

    def test_import_save_and_invalid_import_preserve_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            path.write_text(dump_queue([TypingItem("hello", "café 👋\n\n")]), encoding="utf-8")
            self.window.open_json(path=path)
            self.assertEqual(self.window.description_edit.toPlainText(), "café 👋\n\n")
            saved = Path(directory) / "saved.json"
            with patch("profile_typer.qt_typer.window.QFileDialog.getSaveFileName", return_value=(str(saved), "")):
                self.assertTrue(self.window.save_json(save_as=True))
            self.assertEqual(load_queue(saved), [TypingItem("hello", "café 👋\n\n")])
            path.write_text("{", encoding="utf-8")
            with patch.object(QMessageBox, "warning") as warning:
                self.window.open_json(path=path)
                warning.assert_called_once()
            self.assertEqual(self.window.document.selected.title, "hello")

    def test_preferences_round_trip_without_global_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            preferences.setValue("wpm", 66.5)
            preferences.setValue("delay", 1.5)
            preferences.setValue("advance", False)
            preferences.setValue("cadence_profile_id", "silmoon04-v1")
            extra = TyperWindow(document=TypingDocument(), backend=PreviewTypingBackend(), preferences=preferences)
            self.assertEqual(extra.spins["wpm"].value(), 66.5)
            self.assertFalse(extra.advance_check.isChecked())
            extra.spins["wpm"].setValue(84.5)
            extra.close()
            extra.deleteLater()
            self.assertEqual(float(preferences.value("wpm")), 84.5)

    def test_save_updates_open_file_without_another_file_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            path.write_text('{"title":"one","description":"before"}', encoding="utf-8")
            self.window.open_json(path=path)
            self.window.description_edit.setPlainText("after")
            with patch("profile_typer.qt_typer.window.QFileDialog.getSaveFileName") as dialog:
                self.assertTrue(self.window.save_json())
                dialog.assert_not_called()
            self.assertEqual(load_queue(path)[0].description, "after")
            self.assertFalse(self.window.document.dirty)

    def test_upgrade_replaces_generic_defaults_once(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = QSettings(str(Path(directory) / "legacy.ini"), QSettings.Format.IniFormat)
            for name, value in (("wpm", 100), ("corrections", 0), ("variation", 100), ("delay", 1.5), ("advance", False)):
                preferences.setValue(name, value)
            extra = TyperWindow(backend=PreviewTypingBackend(speedup=50), preferences=preferences)
            self.assertEqual(extra.spins["wpm"].value(), 81.6)
            self.assertEqual(extra.spins["corrections"].value(), 1)
            self.assertEqual(extra.spins["delay"].value(), 1.5)
            self.assertFalse(extra.advance_check.isChecked())
            self.assertEqual(preferences.value("cadence_profile_id"), "silmoon04-v1")
            extra.spins["corrections"].setValue(0)
            extra.close()
            extra.deleteLater()
            restored = TyperWindow(backend=PreviewTypingBackend(), preferences=preferences)
            self.assertEqual(restored.spins["corrections"].value(), 0)
            restored.close()
            restored.deleteLater()
