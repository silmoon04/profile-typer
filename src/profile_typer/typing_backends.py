"""Choose input support for the active desktop without importing other platforms."""
from __future__ import annotations

import os
import sys
import time
from types import SimpleNamespace

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

    def __init__(self):
        self.output = ""

    def targets(self):
        return []

    def escape_pressed(self):
        return False

    def type(self, text, target, settings, stop, progress):
        self.output = ""
        started = time.monotonic()
        for character in text:
            if stop.wait(0.01):
                break
            self.output += character
            progress(len(self.output), len(text), settings.wpm, 0)
        return SimpleNamespace(cancelled=stop.is_set(), keystrokes=len(self.output), net_wpm=settings.wpm,
                               typed_seconds=round(time.monotonic() - started, 2))


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
