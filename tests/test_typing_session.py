from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace

from profile_typer.typing_document import TypingDocument
from profile_typer.typing_session import Phase, TypingSession, TypingSettings


class FakeBackend:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []
        self.escape = False
        self.failure = False

    def escape_pressed(self):
        return self.escape

    def type(self, text, target, settings, stop, progress):
        self.calls.append((text, target, settings))
        self.started.set()
        progress(1, 2, 77, 1)
        if not self.release.wait(2):
            raise TimeoutError("test backend not released")
        if self.failure:
            raise RuntimeError("simulated delivery failure")
        return SimpleNamespace(cancelled=stop.is_set(), keystrokes=len(text), net_wpm=77, typed_seconds=2)


class TypingSessionTests(unittest.TestCase):
    def setUp(self):
        self.document = TypingDocument()
        self.document.update("title never typed", "exact text\n\n")
        self.document.add()
        self.document.navigate(-1)
        self.backend = FakeBackend()
        self.addCleanup(self.backend.release.set)
        self.now = 100.0
        self.session = TypingSession(self.document, self.backend, clock=lambda: self.now)

    def finish(self):
        self.backend.release.set()
        deadline = time.monotonic() + 2
        while self.session.busy and time.monotonic() < deadline:
            self.session.poll()
            time.sleep(0.001)
        self.assertFalse(self.session.busy)

    def test_countdown_uses_injected_clock_and_types_only_description(self):
        self.session.start(TypingSettings(delay=3), 42)
        self.session.poll()
        self.assertEqual(self.backend.calls, [])
        self.now += 2.9
        self.session.poll()
        self.assertEqual(self.backend.calls, [])
        self.now += 0.1
        self.session.poll()
        self.assertTrue(self.backend.started.wait(1))
        self.finish()
        self.assertEqual(self.backend.calls[0][0:2], ("exact text\n\n", 42))
        self.assertEqual(self.session.phase, Phase.DONE)
        self.assertEqual(self.document.selected_index, 1)
        self.assertEqual(self.session.progress, 100)

    def test_cancel_countdown_never_launches(self):
        self.session.start(TypingSettings(delay=10))
        self.session.stop()
        self.now += 100
        self.session.poll()
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.session.phase, Phase.STOPPED)
        self.assertFalse(self.document.locked)

    def test_escape_cancels_countdown(self):
        self.backend.escape = True
        self.session.start(TypingSettings(delay=10))
        self.assertEqual(self.session.phase, Phase.STOPPED)
        self.assertEqual(self.backend.calls, [])

    def test_stop_waits_for_worker_and_ignores_late_progress(self):
        self.session.start(TypingSettings(delay=0))
        self.assertTrue(self.backend.started.wait(1))
        self.session.stop()
        self.session.poll()
        self.assertEqual(self.session.phase, Phase.STOPPING)
        self.assertTrue(self.document.locked)
        with self.assertRaises(ValueError):
            self.session.start(TypingSettings())
        self.finish()
        self.assertEqual(self.session.phase, Phase.STOPPED)
        self.assertEqual(self.document.selected_index, 0)

    def test_worker_exception_unlocks_document_and_keeps_traceback(self):
        self.backend.failure = True
        self.session.start(TypingSettings(delay=0))
        self.finish()
        self.assertEqual(self.session.phase, Phase.FAILED)
        self.assertIn("RuntimeError: simulated delivery failure", self.session.details)
        self.assertFalse(self.document.locked)
        self.assertEqual(self.document.selected_index, 0)

    def test_invalid_settings_never_lock_or_start(self):
        for settings in (TypingSettings(wpm=float("nan")), TypingSettings(delay=-1), TypingSettings(corrections=3)):
            with self.assertRaises(ValueError):
                self.session.start(settings)
            self.assertFalse(self.document.locked)
        self.assertEqual(self.backend.calls, [])

    def test_repeated_runs_have_independent_stop_events(self):
        self.session.start(TypingSettings(delay=0, advance=False))
        self.session.stop()
        self.finish()
        self.session.start(TypingSettings(delay=0, advance=False))
        self.finish()
        self.assertEqual(self.session.phase, Phase.DONE)
        self.assertEqual(len(self.backend.calls), 2)
        self.assertEqual(self.document.selected_index, 0)
