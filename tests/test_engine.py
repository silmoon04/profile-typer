import threading

import pytest

from profile_typer.engine import replay
from profile_typer.typing_session import TypingSettings


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Stop:
    def __init__(self, clock):
        self.clock = clock
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, delay):
        self.clock.now += delay
        return self.stopped


class Port:
    def __init__(self):
        self.output = ""
        self.closed = False
        self.lost_focus = False

    def prepare(self, target):
        self.target = target

    def insert(self, text):
        self.output += text

    def backspace(self):
        self.output = self.output[:-1]

    def cancelled(self):
        return self.lost_focus

    def close(self):
        self.closed = True


class Random:
    def random(self):
        return 0

    def uniform(self, low, high):
        return 0


def test_exact_unicode_multiline_and_generic_pace():
    clock = Clock()
    port = Port()
    result = replay("A\r\n\tcafé 👋\n\n", port, TypingSettings(wpm=60, variation=0), Stop(clock), lambda *_: None, clock=clock)
    assert port.output == "A\n\tcafé 👋\n\n"
    assert result.net_wpm == 60
    assert not result.cancelled
    assert port.closed


def test_corrections_leave_exact_text():
    clock = Clock()
    port = Port()
    result = replay("hello", port, TypingSettings(corrections=2), Stop(clock), lambda *_: None, clock=clock, rng=Random())
    assert port.output == "hello"
    assert result.corrections == 5


def test_focus_change_stops_after_one_character():
    clock = Clock()
    port = Port()

    def progress(*_):
        port.lost_focus = True

    result = replay("long text", port, TypingSettings(), Stop(clock), progress, clock=clock)
    assert result.cancelled and port.closed
    assert port.output == "l"


def test_cancel_before_prepare_sends_nothing():
    port = Port()
    stop = threading.Event()
    stop.set()
    result = replay("text", port, TypingSettings(), stop, lambda *_: None)
    assert result.cancelled
    assert not hasattr(port, "target")
    assert port.output == ""


@pytest.mark.parametrize("text", ["", "bad\ud800", "bad\x00"])
def test_invalid_text_is_rejected_before_input(text):
    port = Port()
    with pytest.raises(ValueError):
        replay(text, port, TypingSettings(), threading.Event(), lambda *_: None)
    assert port.output == ""


def test_failure_closes_port():
    class Broken(Port):
        def insert(self, _text):
            raise RuntimeError("failed")

    port = Broken()
    with pytest.raises(RuntimeError):
        replay("text", port, TypingSettings(), threading.Event(), lambda *_: None)
    assert port.closed
