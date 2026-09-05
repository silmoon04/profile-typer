import threading
import time
from types import SimpleNamespace

from profile_typer.typing_document import TypingDocument
from profile_typer.typing_session import Phase, TypingSession, TypingSettings


class Backend:
    requires_preparation = True

    def __init__(self):
        self.permission = threading.Event()
        self.released = False
        self.typed = False

    def prepare(self, stop):
        while not stop.is_set() and not self.permission.wait(0.01):
            pass

    def release(self):
        self.released = True

    def escape_pressed(self):
        return False

    def type(self, text, target, settings, stop, progress):
        self.typed = True
        self.release()
        return SimpleNamespace(cancelled=False, keystrokes=len(text), net_wpm=60, typed_seconds=1)


def poll_until(session, predicate):
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        session.poll()
        time.sleep(0.005)
    assert predicate()


def test_countdown_starts_after_permission():
    document = TypingDocument()
    document.update("title", "text")
    backend = Backend()
    now = [100.0]
    session = TypingSession(document, backend, clock=lambda: now[0])
    session.start(TypingSettings(delay=3))
    assert session.phase == Phase.PREPARING
    now[0] += 100
    session.poll()
    assert not backend.typed
    backend.permission.set()
    poll_until(session, lambda: session.phase == Phase.COUNTDOWN)
    now[0] += 2.9
    session.poll()
    assert not backend.typed
    now[0] += 0.1
    poll_until(session, lambda: session.phase == Phase.DONE)
    assert backend.typed and backend.released


def test_cancelling_permission_closes_access_without_typing():
    document = TypingDocument()
    document.update("title", "text")
    backend = Backend()
    session = TypingSession(document, backend)
    session.start(TypingSettings())
    session.stop()
    poll_until(session, lambda: not session.busy)
    assert session.phase == Phase.STOPPED
    assert backend.released and not backend.typed
    assert not document.locked


def test_cancelling_after_permission_closes_access():
    document = TypingDocument()
    document.update("title", "text")
    backend = Backend()
    backend.permission.set()
    session = TypingSession(document, backend)
    session.start(TypingSettings(delay=60))
    poll_until(session, lambda: session.phase == Phase.COUNTDOWN)
    session.stop()
    poll_until(session, lambda: not session.busy)
    assert backend.released and not backend.typed
