"""Windows SendInput transport for the shared cadence engine."""
from __future__ import annotations

import os
import ctypes
import time

from . import win32_input as win


class WindowsPort:
    def prepare(self, target):
        self.target = target if target is not None else win.resolve_target(None)
        if not win._user32().IsWindow(self.target):
            raise RuntimeError("The selected window closed. Refresh the destination list.")
        if win._window_pid(self.target) == os.getpid():
            raise RuntimeError("Click a destination outside Profile Typer during the countdown.")
        if target is not None:
            win.focus_window(self.target)
        win.ensure_target_accepts_input(self.target)
        win.ensure_modifiers_released()

    def cancelled(self):
        if escape_pressed():
            return True
        return hasattr(self, "target") and win._root_window(win._user32().GetForegroundWindow() or 0) != win._root_window(self.target)

    def _press(self, stroke, dwell_ms, stop):
        if isinstance(stroke, win.UnicodeUnit):
            flags, key, scan = win.KEYEVENTF_UNICODE, 0, stroke.code_unit
        else:
            flags, key, scan = 0, stroke.virtual_key, stroke.scan_code
        down = win._keyboard_input(flags, key, scan)
        up = win._keyboard_input(flags | win.KEYEVENTF_KEYUP, key, scan)
        library = win._user32()
        if library.SendInput(1, ctypes.byref(down), ctypes.sizeof(down)) != 1:
            raise win.SendError("Windows rejected a key-down event.")
        try:
            (stop.wait if stop is not None else time.sleep)(dwell_ms / 1000)
        finally:
            if library.SendInput(1, ctypes.byref(up), ctypes.sizeof(up)) != 1:
                raise win.SendError("Windows rejected a key-up event.")

    def insert(self, character, *, dwell_ms=0, stop=None):
        strokes = win.build_key_strokes(character)
        if len(strokes) > 1:
            # Keep surrogate pairs together even if cancellation arrives during the hold.
            for stroke in strokes:
                win._send_keystroke(stroke)
            (stop.wait if stop is not None else time.sleep)(dwell_ms / 1000)
        else:
            self._press(strokes[0], dwell_ms, stop)

    def backspace(self, *, dwell_ms=0, stop=None):
        self._press(win.PhysicalKey(0x08, 0x0E), dwell_ms, stop)

    def close(self):
        pass


def targets():
    return [window for window in win.find_windows("") if window.pid != os.getpid()]


def escape_pressed():
    return bool(win._user32().GetAsyncKeyState(0x1B) & 0x8000)
