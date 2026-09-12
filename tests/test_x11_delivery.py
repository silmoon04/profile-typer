import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from profile_typer.typing_backends import X11TypingBackend
from profile_typer.typing_session import TypingSettings

pytestmark = [pytest.mark.x11, pytest.mark.skipif(os.environ.get("PROFILE_TYPER_TEST_X11") != "1", reason="requires isolated Xvfb fixture")]


@pytest.fixture
def receiver(tmp_path):
    path = tmp_path / "received.json"
    process = subprocess.Popen([sys.executable, str(Path(__file__).parent / "fixtures/receiver.py"), str(path)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        handle = int(process.stdout.readline())
        yield process, handle, path
    finally:
        process.terminate()
        process.communicate(timeout=3)


def received(path):
    return json.loads(path.read_text(encoding="utf-8"))["text"]


def test_x11_unicode_tabs_multiline_delivery(receiver):
    process, handle, path = receiver
    expected = "A\n\tcafé 👋\n\n"
    backend = X11TypingBackend()
    assert any(window.hwnd == handle and window.pid == process.pid for window in backend.targets())
    result = backend.type(expected, handle, TypingSettings(wpm=120, variation=0, corrections=0), threading.Event(), lambda *_: None)
    assert not result.cancelled
    deadline = time.monotonic() + 2
    while received(path) != expected and time.monotonic() < deadline:
        time.sleep(0.02)
    assert received(path) == expected


def test_x11_cancel_stops_before_remaining_text(receiver):
    _, handle, path = receiver
    stop = threading.Event()

    def progress(*_):
        stop.set()

    result = X11TypingBackend().type("abc", handle, TypingSettings(corrections=0), stop, progress)
    assert result.cancelled
    time.sleep(0.05)
    assert received(path) == "a"


def test_x11_applies_recorded_word_error_and_backspaces(receiver):
    from profile_typer.cadence import Mulberry32, build_edit_plan
    from profile_typer.engine import replay
    from profile_typer.platforms.x11 import X11Port
    from profile_typer.profiles import recorded_profile
    _, handle, path = receiver
    profile = recorded_profile()
    seed = next(seed for seed in range(100) if any(action.kind == "delete" for action in
                build_edit_plan("the", Mulberry32(seed), correction_amount=1, profile=profile.mistakes)))
    result = replay("the", X11Port(), TypingSettings(wpm=120, variation=0), threading.Event(), lambda *_: None,
                    target=handle, rng=Mulberry32(seed))
    assert not result.cancelled and result.corrections > 0
    assert result.profile_id == "silmoon04-v1"
    time.sleep(0.05)
    result_file = json.loads(path.read_text(encoding="utf-8"))
    assert result_file["text"] == "the"
    assert any(snapshot in profile.mistakes.word_variants["the"] for snapshot in result_file["history"])


def test_custom_view_types_only_clicked_field_and_keeps_view(receiver):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from profile_typer.qt_typer.window import TyperWindow, configure_application
    from profile_typer.typing_document import TypingDocument
    from profile_typer.typing_session import Phase
    _, handle, path = receiver
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    document = TypingDocument()
    document.paste(json.dumps({"views": [{"id": "view", "title": "Grouped answers", "rows": [{"columns": 2, "fields": [
        {"id": "reference", "title": "Reference", "text": "never send this", "actions": ["copy"]},
        {"id": "answer", "title": "Answer", "text": "abc"},
    ]}]}]}))
    window = TyperWindow(document=document, backend=X11TypingBackend())
    window.show()
    app.processEvents()
    window.target_combo.setCurrentIndex(window.target_combo.findData(handle))
    window.spins["delay"].setValue(0)
    window.spins["corrections"].setValue(0)
    window.spins["variation"].setValue(0)
    window.spins["wpm"].setValue(120)
    try:
        window.view_editor.cards["answer"].type_button.click()
        deadline = time.monotonic() + 8
        while window.session.busy and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert window.session.phase == Phase.DONE, window.session.message
        assert received(path) == "abc"
        assert document.selected_id == "view"
        assert document.field("answer").types == 1
        assert document.field("reference").types == 0
    finally:
        window.session.stop()
        document.dirty = False
        window.close()
