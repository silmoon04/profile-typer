"""Choose input support for the active desktop without importing other platforms."""
from __future__ import annotations

import os
import sys
import time

from .engine import replay


class WindowsTypingBackend:
    desktop_note = "Escape or changing the foreground window stops typing."

    def targets(self):
        from .platforms.windows import targets
        return targets()

    def escape_pressed(self):
        from .platforms.windows import escape_pressed
        return escape_pressed()

    def type(self, text, target, settings, stop, progress):
        from .platforms.windows import WindowsPort
        return replay(text, WindowsPort(), settings, stop, progress, target=target)


class X11TypingBackend:
    desktop_note = "X11: Escape or changing the foreground window stops typing."

    def targets(self):
        from .platforms.x11 import targets
        return targets()

    def escape_pressed(self):
        from .platforms.x11 import escape_pressed
        return escape_pressed()

    def type(self, text, target, settings, stop, progress):
        from .platforms.x11 import X11Port
        return replay(text, X11Port(), settings, stop, progress, target=target)


class PreviewTypingBackend:
    desktop_note = "Preview mode: no input is sent to other applications."

    def __init__(self, *, speedup=1.0):
        self.output = ""
        self.speedup = max(1.0, float(speedup))

    def targets(self):
        return []

    def escape_pressed(self):
        return False

    def type(self, text, target, settings, stop, progress):
        self.output = ""
        backend = self

        class ScaledStop:
            def is_set(self):
                return stop.is_set()

            def wait(self, seconds):
                return stop.wait(seconds / backend.speedup)

        class PreviewPort:
            def prepare(self, _target):
                pass

            def cancelled(self):
                return False

            def insert(self, character, *, dwell_ms, stop):
                backend.output += character
                stop.wait(dwell_ms / 1000)

            def backspace(self, *, dwell_ms, stop):
                backend.output = backend.output[:-1]
                stop.wait(dwell_ms / 1000)

            def close(self):
                pass

        return replay(text, PreviewPort(), settings, ScaledStop(), progress,
                      clock=lambda: time.monotonic() * backend.speedup)


def default_backend():
    if sys.platform == "win32":
        return WindowsTypingBackend()
    if sys.platform.startswith("linux"):
        session_type = os.environ.get("XDG_SESSION_TYPE")
        if session_type == "wayland" or (session_type != "x11" and os.environ.get("WAYLAND_DISPLAY")):
            from .platforms.wayland import WaylandTypingBackend
            return WaylandTypingBackend()
        return X11TypingBackend()
    raise RuntimeError("Typing is supported on Windows and Linux. Use --dry-run to preview on other systems.")
