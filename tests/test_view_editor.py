import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from profile_typer.qt_typer.window import TyperWindow, configure_application
from profile_typer.typing_backends import PreviewTypingBackend
from profile_typer.typing_document import TypingDocument


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    document = TypingDocument()
    document.paste(json.dumps({"views": [
        {"id": "repo", "title": "Repository", "rows": [{"columns": 2, "fields": [
            {"id": "task", "title": "Task ID", "text": "hello\n\n"},
            {"id": "url", "title": "URL", "text": "https://example.org", "actions": ["copy"]},
        ]}, {"fields": [{"id": "options", "title": "Options", "options": ["One", "Two", "Three"], "selected": ["One", "Two"], "multiple": True, "option_columns": 2}]}]},
        {"id": "next", "title": "Next", "rows": [[{"title": "Reason", "text": "later"}]]},
    ]}))
    window = TyperWindow(document=document, backend=PreviewTypingBackend(speedup=50))
    window.resize(1100, 1000)
    window.show()
    app.processEvents()
    QTest.qWait(80)
    yield window
    window.session.stop()
    deadline = time.monotonic() + 3
    while window.session.busy and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    window.document.dirty = False
    window.close()
    window.deleteLater()
    app.processEvents()


def test_copy_counter_and_exact_clipboard_value(window):
    card = window.view_editor.cards["url"]
    QTest.mouseClick(card.copy_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(card.copy_button, Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == "https://example.org"
    assert card.copy_button.text() == "Copied 2"
    assert window.document.field("task").copies == 0
    assert not card.type_button.isVisible()


def test_selected_text_copy_is_counted(window):
    editor = window.view_editor.cards["task"].editor
    editor.setFocus()
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(3, cursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "hel"
    assert window.document.field("task").copies == 1


def test_copying_part_of_option_label_is_counted(window):
    label = window.view_editor.cards["options"].option_labels[0]
    label.setFocus()
    label.setSelection(0, 2)
    QTest.keyClick(label, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "On"
    assert window.document.field("options").copies == 1
    assert window.document.field("options").value == "One\nTwo"


def test_cancelled_field_start_is_not_shown_as_done(window):
    window.spins["delay"].setValue(10)
    window.view_editor.cards["task"].type_button.click()
    window.stop_button.click()
    assert window.document.field("task").types == 1
    assert window.document.field("task").status == "Stopped"
    assert window.document.selected_id == "repo"


def test_field_type_uses_its_value_and_stays_in_view(window):
    window.spins["delay"].setValue(0)
    card = window.view_editor.cards["task"]
    QTest.mouseClick(card.type_button, Qt.MouseButton.LeftButton)
    assert window.document.field("task").types == 1
    assert not window.view_editor.cards["url"].copy_button.isEnabled()
    deadline = time.monotonic() + 3
    while window.session.busy and time.monotonic() < deadline:
        QApplication.processEvents()
        QTest.qWait(5)
    assert window.backend.output == "hello\n\n"
    assert window.document.selected_id == "repo"
    assert window.document.field("task").status == "Done"
    assert card.type_button.text() == "Type 1"


def test_options_toggle_and_custom_answer(window):
    card = window.view_editor.cards["options"]
    QTest.mouseClick(card.option_buttons[2], Qt.MouseButton.LeftButton)
    assert window.document.field("options").value == "One\nTwo\nThree"
    assert card.selected_label.text() == "3 selected"
    card.edit_answer_button.click()
    card.editor.setPlainText("custom value")
    assert window.document.field("options").value == "custom value"
    assert all(not button.isChecked() for button in card.option_buttons)
    card.copy_button.click()
    assert QApplication.clipboard().text() == "custom value"


def test_edits_survive_navigation_and_keep_undo_cursor(window):
    card = window.view_editor.cards["task"]
    card.editor.setFocus()
    card.editor.selectAll()
    QTest.keyClicks(card.editor, "new text")
    card.editor.undo()
    assert card.editor.toPlainText() != "new text"
    card.editor.setPlainText("new text\n")
    window.navigate(1)
    window.navigate(-1)
    assert window.view_editor.cards["task"].editor.toPlainText() == "new text\n"


def test_navigation_preserves_editor_selection_and_undo_history(window):
    editor = window.view_editor.cards["task"].editor
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "draft")
    cursor = editor.textCursor()
    cursor.setPosition(1)
    cursor.setPosition(4, cursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    window.navigate(1)
    window.navigate(-1)
    restored = window.view_editor.cards["task"].editor
    assert restored.textCursor().selectedText() == "raf"
    restored.undo()
    assert window.document.field("task").value == "hello\n\n"


def test_option_label_click_selects_without_copying(window):
    card = window.view_editor.cards["options"]
    QTest.mouseClick(card.option_labels[2], Qt.MouseButton.LeftButton)
    assert window.document.field("options").selected == ("One", "Two", "Three")
    assert window.document.field("options").copies == 0


def test_rows_reflow_and_scrollbars_only_appear_when_needed(window):
    pane = window.view_editor
    assert pane.rows[0].effective_columns == 2
    assert pane.verticalScrollBar().maximum() == 0
    window.resize(380, 420)
    QApplication.processEvents()
    QTest.qWait(100)
    assert pane.rows[0].effective_columns == 1
    assert pane.verticalScrollBar().maximum() > 0
    assert pane.horizontalScrollBar().maximum() == 0
    for widget in [window.stop_button, window.target_combo, *window.spins.values()]:
        point = widget.mapTo(window, QPoint(0, 0))
        assert widget.isVisible()
        assert point.y() + widget.height() <= window.height()
    window.resize(1100, 1000)
    QApplication.processEvents()
    QTest.qWait(100)
    assert pane.verticalScrollBar().maximum() == 0


def test_long_text_and_markup_are_plain_editable_content(window):
    text = "<script>not executed</script> " + "long text " * 500
    window.document.update_field("task", text)
    window.refresh()
    window.resize(380, 420)
    QApplication.processEvents()
    QTest.qWait(100)
    assert window.view_editor.cards["task"].editor.toPlainText() == text
    assert window.view_editor.horizontalScrollBar().maximum() == 0


def test_field_header_wraps_title_and_keeps_actions_inside_card(window):
    window.document.paste(json.dumps({"views": [{"title": "Long labels", "rows": [[{
        "id": "long", "title": "A long title that needs several lines in a narrow window", "text": "Answer"
    }]]}]}))
    window.refresh()
    window.resize(380, 500)
    QApplication.processEvents()
    QTest.qWait(100)
    card = window.view_editor.cards["long"]
    assert card.title_label.height() >= 2 * card.title_label.fontMetrics().height()
    assert card.title_label.x() + card.title_label.width() <= card.copy_button.x()
    assert card.type_button.x() + card.type_button.width() < card.width()
    assert window.view_editor.horizontalScrollBar().maximum() == 0


def test_short_choices_share_row_and_hide_single_choice_count(window):
    window.document.paste(json.dumps({"views": [{"title": "Choice", "rows": [[{
        "id": "choice", "title": "A", "options": ["YES", "NO"], "selected": "YES"
    }]]}]}))
    window.refresh()
    QApplication.processEvents()
    QTest.qWait(50)
    card = window.view_editor.cards["choice"]
    assert card.option_grid.effective_columns == 2
    assert not card.selected_label.isVisible()
    assert abs(card.title_label.y() - card.copy_button.y()) < card.copy_button.height()
    card.option_labels[0].setFocus()
    QApplication.processEvents()
    assert card.property("active") is True


def test_reopening_same_ids_refreshes_layout_and_labels(window, tmp_path):
    replacement = {"views": [{"id": "repo", "title": "Revised repository", "color": "purple", "rows": [
        {"columns": 1, "fields": [
            {"id": "task", "title": "New task label", "text": "revised answer", "actions": ["copy"]},
            {"id": "url", "title": "New URL label", "text": "https://example.org/new"},
        ]},
        {"fields": [{"id": "options", "title": "New options", "options": ["YES", "NO"], "selected": "YES"}]},
    ]}]}
    path = tmp_path / "revised.json"
    path.write_text(json.dumps(replacement), encoding="utf-8")
    window.document.dirty = False
    window.open_json(path=path)
    QApplication.processEvents()
    assert window.title_edit.text() == "Revised repository"
    assert window.view_editor.rows[0].effective_columns == 1
    task = window.view_editor.cards["task"]
    assert task.title_label.text() == "New task label"
    assert task.editor.toPlainText() == "revised answer"
    assert not task.type_button.isVisible()
    assert task.view_color == "purple"
    options = window.view_editor.cards["options"]
    assert [label.text() for label in options.option_labels] == ["YES", "NO"]
    assert options.option_buttons[0].isChecked()
    options.copy_button.click()
    assert QApplication.clipboard().text() == "YES"
    replacement["views"][0]["rows"][1]["fields"][0].update(selected=[], text="Custom answer")
    path.write_text(json.dumps(replacement), encoding="utf-8")
    window.document.dirty = False
    window.open_json(path=path)
    assert options.editor.isVisible()
    assert options.editor.toPlainText() == "Custom answer"
