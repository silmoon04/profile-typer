"""X11 discovery and focus checks, with xdotool for Unicode XTEST delivery."""
from __future__ import annotations

import os
import math
import shutil
import subprocess

from profile_typer.engine import WindowTarget


def connection():
    from Xlib.display import Display
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("No X11 display is available. Start Profile Typer in your desktop session.")
    return Display()


def _property(display, window, name):
    from Xlib import X
    value = window.get_full_property(display.intern_atom(name), X.AnyPropertyType)
    return value.value if value is not None else None


def active_window(display):
    value = _property(display, display.screen().root, "_NET_ACTIVE_WINDOW")
    if value is not None and len(value):
        return int(value[0])
    focus = display.get_input_focus().focus
    return focus.id if hasattr(focus, "id") else 0


def _escape(display):
    from Xlib import XK
    code = display.keysym_to_keycode(XK.XK_Escape)
    keys = display.query_keymap()
    return bool(keys[code // 8] & (1 << (code % 8)))


def escape_pressed():
    display = connection()
    try:
        return _escape(display)
    finally:
        display.close()


def targets():
    from Xlib.error import XError
    display = connection()
    try:
        ids = _property(display, display.screen().root, "_NET_CLIENT_LIST")
        if ids is None:
            ids = [child.id for child in display.screen().root.query_tree().children]
        result = []
        for handle in ids:
            try:
                window = display.create_resource_object("window", int(handle))
                title = _property(display, window, "_NET_WM_NAME")
                if isinstance(title, bytes):
                    title = title.decode("utf-8", errors="replace")
                title = title or window.get_wm_name() or ""
                pid_value = _property(display, window, "_NET_WM_PID")
                pid = int(pid_value[0]) if pid_value is not None and len(pid_value) else 0
                if title and pid != os.getpid() and window.get_attributes().map_state == 2:
                    result.append(WindowTarget(int(handle), pid, str(title)))
            except XError:
                continue
        return result
    finally:
        display.close()


class X11Port:
    def __init__(self):
        self.display = None
        self.command = shutil.which("xdotool")

    def _run(self, *arguments, text=None):
        if not self.command:
            raise RuntimeError("Install X11 input support with: sudo apt install xdotool")
        result = subprocess.run([self.command, *arguments], input=text, text=True, encoding="utf-8",
                                capture_output=True, timeout=5, check=False, env={**os.environ, "LC_ALL": "C.UTF-8"})
        if result.returncode:
            raise RuntimeError("X11 input failed. Check that the destination window is still open and focused.")

    def prepare(self, target):
        self.display = connection()
        self.target = target if target is not None else active_window(self.display)
        if not self.target:
            raise RuntimeError("Click a destination window during the countdown.")
        window = self.display.create_resource_object("window", self.target)
        pid = _property(self.display, window, "_NET_WM_PID")
        if pid is not None and len(pid) and int(pid[0]) == os.getpid():
            raise RuntimeError("Click a destination outside Profile Typer during the countdown.")
        if target is not None:
            self._run("windowactivate", "--sync", str(target))
        if active_window(self.display) != self.target:
            raise RuntimeError("Could not focus the selected destination window.")

    def cancelled(self):
        return self.display is not None and (_escape(self.display) or active_window(self.display) != self.target)

    def _press(self, symbol, dwell_ms):
        # Only generated keysym names and numeric durations enter this command stream.
        # The input description never becomes command syntax or process arguments.
        script = f"keydown --delay 0 {symbol}\nsleep {max(8, dwell_ms) / 1000:.6f}\nkeyup --delay 0 {symbol}\n"
        try:
            self._run("-", text=script)
        except Exception:
            self._run("-", text=f"keyup --delay 0 {symbol}\n")
            raise

    def insert(self, character, *, dwell_ms=0, stop=None):
        if not character.isascii():
            # xdotool's text path keeps temporary Unicode mappings valid while held.
            self._run("type", "--delay", str(max(12, math.ceil(dwell_ms * 2))), "--file", "-", text=character)
            return
        symbol = {"\n": "Return", "\t": "Tab"}.get(character, f"U{ord(character):04X}")
        self._press(symbol, dwell_ms)

    def backspace(self, *, dwell_ms=0, stop=None):
        self._press("BackSpace", dwell_ms)

    def close(self):
        if self.display is not None:
            self.display.close()
            self.display = None
