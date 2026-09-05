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
    result = backend.type(expected, handle, TypingSettings(wpm=120, variation=0), threading.Event(), lambda *_: None)
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

    result = X11TypingBackend().type("abc", handle, TypingSettings(), stop, progress)
    assert result.cancelled
    time.sleep(0.05)
    assert received(path) == "a"
