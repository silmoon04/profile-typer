"""Windows SendInput adapter. No tracker, recorded profiles, or private storage."""
from __future__ import annotations

import os

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

    def insert(self, character):
        for stroke in win.build_key_strokes(character):
            win._send_keystroke(stroke)

    def backspace(self):
        win._send_keystroke(win.PhysicalKey(0x08, 0x0E))

    def close(self):
        pass


def targets():
    return [window for window in win.find_windows("") if window.pid != os.getpid()]


def escape_pressed():
    return bool(win._user32().GetAsyncKeyState(0x1B) & 0x8000)
