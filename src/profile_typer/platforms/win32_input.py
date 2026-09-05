"""Windows Unicode input using SendInput, with focus and modifier checks."""

from __future__ import annotations

import ctypes
import dataclasses
import functools
import sys
import time
from ctypes import wintypes

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

GA_ROOT = 2
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION = 20
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_TAB_SCAN_CODE = 0x0F
_RETURN_SCAN_CODE = 0x1C
_HELD_MODIFIERS = (
    (VK_SHIFT, "Shift"),
    (VK_CONTROL, "Ctrl"),
    (VK_MENU, "Alt"),
    (VK_LWIN, "Win"),
    (VK_RWIN, "Win"),
)


class TyperError(RuntimeError):
    """A text-injection step failed before or during delivery."""


class SendError(TyperError):
    """Windows rejected one or more injected input events."""


class FocusError(TyperError):
    """A target window could not be resolved or brought to the foreground."""


class ElevationError(TyperError):
    """The target window runs at an integrity level that rejects our input."""


class ModifiersHeldError(TyperError):
    """A physical modifier key is held, which would corrupt injected text."""


@dataclasses.dataclass(frozen=True, slots=True)
class UnicodeUnit:
    """One UTF-16 code unit delivered as a ``KEYEVENTF_UNICODE`` pair."""

    code_unit: int


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalKey:
    """A named key delivered as a virtual-key down/up pair."""

    virtual_key: int
    scan_code: int


KeyStroke = UnicodeUnit | PhysicalKey


@dataclasses.dataclass(frozen=True, slots=True)
class WindowInfo:
    hwnd: int
    pid: int
    title: str


@dataclasses.dataclass(frozen=True, slots=True)
class TypeResult:
    keystrokes: int
    hwnd: int
    title: str


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTunion)]


def build_key_strokes(text: str) -> tuple[KeyStroke, ...]:
    """Translate text into the keystroke sequence ``SendInput`` will deliver.

    ``\\r\\n`` and ``\\r`` collapse to a single Return press, ``\\t`` becomes a
    real Tab press, every BMP character becomes one UTF-16 code unit, and
    astral-plane characters split into their surrogate pair.
    """
    strokes: list[KeyStroke] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for character in normalized:
        if character == "\n":
            strokes.append(PhysicalKey(VK_RETURN, _RETURN_SCAN_CODE))
        elif character == "\t":
            strokes.append(PhysicalKey(VK_TAB, _TAB_SCAN_CODE))
        else:
            strokes.extend(UnicodeUnit(unit) for unit in _utf16_code_units(character))
    return tuple(strokes)


def _utf16_code_units(character: str) -> tuple[int, ...]:
    code_point = ord(character)
    if 0xD800 <= code_point <= 0xDFFF:
        raise ValueError("text contains an unpaired surrogate code point")
    if code_point <= 0xFFFF:
        return (code_point,)
    offset = code_point - 0x10000
    return (0xD800 + (offset >> 10), 0xDC00 + (offset & 0x3FF))


def parse_window_query(query: str) -> tuple[str, int | None]:
    """Return ``("pid", pid)`` for ``pid:N`` queries, else ``("title", None)``."""
    if query.startswith("pid:"):
        raw = query[4:]
        try:
            pid = int(raw)
        except ValueError as error:
            raise ValueError(f"pid query must be an integer, got {raw!r}") from error
        if pid <= 0:
            raise ValueError(f"pid query must be positive, got {pid}")
        return ("pid", pid)
    return ("title", None)


@functools.lru_cache(maxsize=1)
def _user32() -> ctypes.WinDLL:
    if sys.platform != "win32":
        raise TyperError("OS text injection requires Windows")
    library = ctypes.WinDLL("user32", use_last_error=True)
    library.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
    library.SendInput.restype = wintypes.UINT
    library.GetForegroundWindow.restype = wintypes.HWND
    library.SetForegroundWindow.argtypes = (wintypes.HWND,)
    library.SetForegroundWindow.restype = wintypes.BOOL
    library.BringWindowToTop.argtypes = (wintypes.HWND,)
    library.SetFocus.argtypes = (wintypes.HWND,)
    library.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    library.GetWindowThreadProcessId.restype = wintypes.DWORD
    library.GetWindowTextW.argtypes = (wintypes.HWND, ctypes.POINTER(ctypes.c_wchar), ctypes.c_int)
    library.GetWindowTextW.restype = ctypes.c_int
    library.EnumWindows.argtypes = (ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM)
    library.EnumWindows.restype = wintypes.BOOL
    library.IsWindowVisible.argtypes = (wintypes.HWND,)
    library.IsWindowVisible.restype = wintypes.BOOL
    library.IsWindow.argtypes = (wintypes.HWND,)
    library.IsWindow.restype = wintypes.BOOL
    library.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    library.GetAncestor.restype = wintypes.HWND
    library.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    library.AttachThreadInput.restype = wintypes.BOOL
    library.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    library.GetAsyncKeyState.restype = ctypes.c_short
    return library


@functools.lru_cache(maxsize=1)
def _kernel32() -> ctypes.WinDLL:
    if sys.platform != "win32":
        raise TyperError("OS text injection requires Windows")
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.GetCurrentThreadId.restype = wintypes.DWORD
    library.GetCurrentProcess.restype = wintypes.HANDLE
    library.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    library.OpenProcess.restype = wintypes.HANDLE
    library.CloseHandle.argtypes = (wintypes.HANDLE,)
    return library


@functools.lru_cache(maxsize=1)
def _advapi32() -> ctypes.WinDLL:
    if sys.platform != "win32":
        raise TyperError("OS text injection requires Windows")
    library = ctypes.WinDLL("advapi32", use_last_error=True)
    library.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    library.OpenProcessToken.restype = wintypes.BOOL
    library.GetTokenInformation.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    library.GetTokenInformation.restype = wintypes.BOOL
    return library


def window_title(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    _user32().GetWindowTextW(hwnd, buffer, 512)
    return buffer.value


def list_windows() -> tuple[WindowInfo, ...]:
    """Return all visible top-level windows that have a title."""
    found: list[WindowInfo] = []

    def on_window(hwnd: int, _lparam: int) -> bool:
        if _user32().IsWindowVisible(hwnd):
            title = window_title(hwnd)
            if title:
                found.append(WindowInfo(hwnd=hwnd, pid=_window_pid(hwnd), title=title))
        return True

    _user32().EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(on_window), 0)
    return tuple(found)


def find_windows(query: str) -> tuple[WindowInfo, ...]:
    """Match windows by exact pid (``pid:N``) or case-insensitive title substring."""
    kind, pid = parse_window_query(query)
    if kind == "pid":
        return tuple(window for window in list_windows() if window.pid == pid)
    needle = query.casefold()
    return tuple(window for window in list_windows() if needle in window.title.casefold())


def resolve_target(query: str | None) -> int:
    """Resolve a window query to one hwnd; ``None`` means current foreground."""
    if query is None:
        hwnd = _user32().GetForegroundWindow()
        if not hwnd:
            raise FocusError("no window currently has keyboard focus")
        return hwnd
    matches = find_windows(query)
    if not matches:
        raise FocusError(f"no visible window matches {query!r}; run with --list-windows to inspect candidates")
    if len(matches) > 1:
        shown = "\n  ".join(f"hwnd={w.hwnd} pid={w.pid} {w.title}" for w in matches[:8])
        raise FocusError(f"{len(matches)} windows match {query!r}; disambiguate with pid:\n  {shown}")
    return matches[0].hwnd


def focus_window(hwnd: int, *, attempts: int = 20, pause_s: float = 0.05) -> None:
    """Bring a window to the foreground, or raise :class:`FocusError`."""
    library = _user32()
    target_root = _root_window(hwnd)
    for _ in range(attempts):
        if _root_window(library.GetForegroundWindow() or 0) == target_root:
            return
        _attach_and_raise(target_root)
        time.sleep(pause_s)
    current = window_title(library.GetForegroundWindow() or 0)
    raise FocusError(f"could not bring {window_title(target_root)!r} to the foreground; foreground is {current!r}")


def _attach_and_raise(target_root: int) -> None:
    library = _user32()
    current_thread = _kernel32().GetCurrentThreadId()
    foreground = library.GetForegroundWindow() or 0
    foreground_thread = library.GetWindowThreadProcessId(foreground, None) if foreground else 0
    target_thread = library.GetWindowThreadProcessId(target_root, None)
    attached: list[tuple[int, int]] = []
    if foreground_thread and foreground_thread != current_thread:
        if library.AttachThreadInput(foreground_thread, current_thread, True):
            attached.append((foreground_thread, current_thread))
    if target_thread and target_thread != current_thread:
        if library.AttachThreadInput(target_thread, current_thread, True):
            attached.append((target_thread, current_thread))
    try:
        library.BringWindowToTop(target_root)
        library.SetForegroundWindow(target_root)
        library.SetFocus(target_root)
    finally:
        for owner, guest in reversed(attached):
            library.AttachThreadInput(owner, guest, False)


def _root_window(hwnd: int) -> int:
    return _user32().GetAncestor(hwnd, GA_ROOT) or hwnd


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def ensure_modifiers_released() -> None:
    """Refuse to type while a physical modifier key is held down."""
    library = _user32()
    held = [name for virtual_key, name in _HELD_MODIFIERS if library.GetAsyncKeyState(virtual_key) & 0x8000]
    if held:
        raise ModifiersHeldError(f"release these keys before injecting text: {', '.join(held)}")


def ensure_target_accepts_input(hwnd: int) -> None:
    """Fail loudly when the target would silently drop injected input."""
    target_pid = _window_pid(hwnd)
    target_process = _kernel32().OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, target_pid)
    target_elevated = _process_token_elevated(target_process, close_process=target_process is not None)
    self_elevated = _process_token_elevated(_kernel32().GetCurrentProcess(), close_process=False)
    if target_elevated and self_elevated is False:
        raise ElevationError(
            f"{window_title(hwnd)!r} (pid {target_pid}) runs elevated; injected input would be dropped. "
            "Restart this console as administrator to type into it."
        )


def _process_token_elevated(process: wintypes.HANDLE | None, *, close_process: bool) -> bool | None:
    """Return token elevation for a process handle, or None when unknown."""
    if not process:
        return None
    kernel32 = _kernel32()
    advapi32 = _advapi32()
    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            return None
        elevation = wintypes.DWORD(0)
        returned = wintypes.DWORD(0)
        ok = advapi32.GetTokenInformation(
            token, TOKEN_ELEVATION, ctypes.byref(elevation), ctypes.sizeof(elevation), ctypes.byref(returned)
        )
        return bool(elevation.value) if ok else None
    finally:
        if token:
            kernel32.CloseHandle(token)
        if close_process:
            kernel32.CloseHandle(process)


def type_text(
    text: str,
    target: str | None = None,
    *,
    inter_key_delay_s: float = 0.0,
    move_focus: bool = True,
    check_modifiers: bool = True,
    check_elevation: bool = True,
) -> TypeResult:
    """Type ``text`` into ``target`` (or the current foreground window).

    ``target`` accepts a title substring or ``pid:N``.  The window is focused
    first, elevation and held-modifier guards run by default, and every
    keystroke goes through :function:`SendInput` as a down/up pair.
    """
    if inter_key_delay_s < 0:
        raise ValueError("inter_key_delay_s must be non-negative")
    strokes = build_key_strokes(text)
    hwnd = resolve_target(target)
    if move_focus and target is not None:
        focus_window(hwnd)
    if check_elevation:
        ensure_target_accepts_input(hwnd)
    if check_modifiers:
        ensure_modifiers_released()
    for stroke in strokes:
        _send_keystroke(stroke)
        if inter_key_delay_s:
            time.sleep(inter_key_delay_s)
    return TypeResult(keystrokes=len(strokes), hwnd=hwnd, title=window_title(hwnd))


def _send_keystroke(stroke: KeyStroke) -> None:
    if isinstance(stroke, UnicodeUnit):
        down = _keyboard_input(KEYEVENTF_UNICODE, 0, stroke.code_unit)
        up = _keyboard_input(KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, stroke.code_unit)
    else:
        down = _keyboard_input(0, stroke.virtual_key, stroke.scan_code)
        up = _keyboard_input(KEYEVENTF_KEYUP, stroke.virtual_key, stroke.scan_code)
    sequence = (_INPUT * 2)(down, up)
    sent = _user32().SendInput(2, sequence, ctypes.sizeof(_INPUT))
    if sent != 2:
        raise SendError(f"SendInput accepted {sent} of 2 events (GetLastError={ctypes.get_last_error()})")


def _keyboard_input(flags: int, virtual_key: int, scan: int) -> _INPUT:
    item = _INPUT()
    item.type = INPUT_KEYBOARD
    item.ki = _KEYBDINPUT(virtual_key, scan, flags, 0, None)
    return item
