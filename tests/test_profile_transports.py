from unittest.mock import patch
import threading

from profile_typer.platforms.windows import WindowsPort
from profile_typer.platforms import win32_input


def test_windows_hold_is_interruptible_and_key_up_is_sent():
    stop = threading.Event()
    flags = []

    class Library:
        def SendInput(self, _count, pointer, _size):
            flags.append(pointer._obj.ki.dwFlags)
            stop.set()
            return 1

    with patch.object(win32_input, "_user32", return_value=Library()):
        WindowsPort().insert("a", dwell_ms=450, stop=stop)
    assert flags == [win32_input.KEYEVENTF_UNICODE, win32_input.KEYEVENTF_UNICODE | win32_input.KEYEVENTF_KEYUP]
