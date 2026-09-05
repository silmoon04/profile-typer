"""Typing lifecycle with an injectable engine and clock. No GUI or Windows imports."""
from __future__ import annotations

import math
import queue
import threading
import time
import traceback
from types import SimpleNamespace
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol

from .typing_document import TypingDocument


@dataclass(frozen=True)
class TypingSettings:
    wpm: float = 100
    corrections: float = 0
    variation: float = 100
    delay: float = 3
    advance: bool = True

    def validate(self) -> None:
        for label, value, low, high in (("Speed", self.wpm, 15, 120), ("Corrections", self.corrections, 0, 2),
                                        ("Variation", self.variation, 0, 150), ("Start delay", self.delay, 0, 60)):
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{label} must be between {low:g} and {high:g}.")


class TypingBackend(Protocol):
    def targets(self) -> list[Any]: ...
    def escape_pressed(self) -> bool: ...
    def type(self, text: str, target: int | None, settings: TypingSettings,
             stop: threading.Event, progress: Callable[[int, int, float, int], None]) -> Any: ...


class Phase(str, Enum):
    READY = "Ready"
    PREPARING = "Permission"
    COUNTDOWN = "Countdown"
    TYPING = "Typing"
    STOPPING = "Stopping"
    DONE = "Done"
    STOPPED = "Stopped"
    FAILED = "Failed"


class TypingSession:
    def __init__(self, document: TypingDocument, backend: TypingBackend, *, clock: Callable[[], float] = time.monotonic):
        self.document = document
        self.backend = backend
        self.clock = clock
        self.phase = Phase.READY
        self.message = "Ready. Open a queue or enter a description."
        self.progress = 0.0
        self.details = ""
        self.history: deque[str] = deque(maxlen=100)
        self._events: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._outcome: tuple[str, Any] | None = None

    @property
    def busy(self) -> bool:
        return self.phase in (Phase.PREPARING, Phase.COUNTDOWN, Phase.TYPING, Phase.STOPPING)

    def _transition(self, phase: Phase, message: str) -> None:
        self.history.append(f"{self.clock():.3f}: {self.phase.value} -> {phase.value}")
        self.phase = phase
        self.message = message

    def start(self, settings: TypingSettings, target: int | None = None) -> None:
        if self.busy:
            raise ValueError("A typing run is already active.")
        settings.validate()
        self._entry = self.document.begin_run()
        self._settings = settings
        self._target = target
        self._stop = threading.Event()
        self._events = queue.SimpleQueue()
        self._outcome = None
        self._worker = None
        self.progress = 0
        self.details = ""
        if getattr(self.backend, "requires_preparation", False):
            self._transition(Phase.PREPARING, "Allow keyboard access in the desktop dialog. The countdown starts after permission.")

            def prepare():
                try:
                    self.backend.prepare(self._stop)
                    self._events.put(("prepared", None))
                except Exception as error:
                    self._events.put(("error", (str(error), traceback.format_exc())))

            self._worker = threading.Thread(target=prepare, name="typer-permission", daemon=True)
            self._worker.start()
            return
        self._deadline = self.clock() + settings.delay
        self._transition(Phase.COUNTDOWN, "Click the destination text field during the countdown.")
        self.poll()

    def stop(self) -> None:
        if not self.busy or self.phase == Phase.STOPPING:
            return
        self._stop.set()
        if self.phase == Phase.COUNTDOWN:
            if getattr(self.backend, "requires_preparation", False):
                self._release_prepared()
            else:
                self._finish(Phase.STOPPED, "Cancelled before typing.")
        else:
            self._transition(Phase.STOPPING, "Stopping. Waiting for the typing worker to finish.")

    def _launch(self) -> None:
        self.document.set_run_status(self._entry.id, "Typing")
        self._transition(Phase.TYPING, getattr(self.backend, "desktop_note", "Typing the selected description."))
        text, target, settings, stop, events = self._entry.description, self._target, self._settings, self._stop, self._events

        def run() -> None:
            try:
                result = self.backend.type(text, target, settings, stop,
                                           lambda *values: events.put(("progress", values)))
                events.put(("result", result))
            except Exception as error:
                events.put(("error", (str(error), traceback.format_exc())))

        self._worker = threading.Thread(target=run, name="profile-typer", daemon=True)
        self._worker.start()

    def _release_prepared(self):
        self._transition(Phase.STOPPING, "Closing desktop keyboard access.")

        def release():
            try:
                self.backend.release()
                self._events.put(("result", SimpleNamespace(cancelled=True)))
            except Exception as error:
                self._events.put(("error", (str(error), traceback.format_exc())))

        self._worker = threading.Thread(target=release, name="typer-permission-close", daemon=True)
        self._worker.start()

    def poll(self) -> None:
        if self.phase == Phase.COUNTDOWN:
            try:
                if self.backend.escape_pressed():
                    self.stop()
                    return
                remaining = max(0, self._deadline - self.clock())
                self.message = f"Starting in {remaining:.1f}s. Click the destination field."
                if remaining == 0:
                    self._launch()
            except Exception as error:
                self.details = traceback.format_exc()
                self._finish(Phase.FAILED, str(error))
                return
        for _ in range(200):
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress" and self.phase == Phase.TYPING:
                done, total, wpm, corrections = payload
                self.progress = min(100, max(0, 100 * done / max(total, 1)))
                self.message = f"Typing: {done}/{total} actions · {wpm:.0f} WPM · {corrections} corrections"
            elif kind in ("result", "error", "prepared"):
                self._outcome = (kind, payload)
        if self._outcome is not None and self._worker is not None and not self._worker.is_alive():
            kind, payload = self._outcome
            self._outcome = None
            if kind == "prepared":
                if self._stop.is_set():
                    self._release_prepared()
                else:
                    self._worker = None
                    self._deadline = self.clock() + self._settings.delay
                    self._transition(Phase.COUNTDOWN, "Keyboard access granted. Choose the destination during the countdown.")
            elif kind == "error":
                message, self.details = payload
                self._finish(Phase.FAILED, f"Typing failed: {message}")
            elif payload.cancelled or self._stop.is_set():
                self._finish(Phase.STOPPED, "Stopped. Starting again types this description from the beginning.")
            else:
                self.progress = 100
                self._finish(Phase.DONE, f"Done: {payload.keystrokes} keystrokes · {payload.net_wpm:g} WPM · {payload.typed_seconds:g}s")

    def _finish(self, phase: Phase, message: str) -> None:
        self.document.finish_run(self._entry.id, phase.value, advance=self._settings.advance)
        self._transition(phase, message)
