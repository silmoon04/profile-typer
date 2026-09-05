from unittest.mock import patch

from profile_typer.typing_backends import WindowsTypingBackend, X11TypingBackend, default_backend


def test_windows_backend_is_selected_without_linux_imports():
    with patch("sys.platform", "win32"):
        assert isinstance(default_backend(), WindowsTypingBackend)


def test_explicit_x11_session_wins_over_stale_wayland_environment(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    with patch("sys.platform", "linux"):
        assert isinstance(default_backend(), X11TypingBackend)


def test_wayland_never_falls_back_to_x11_injection(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":1")
    with patch("sys.platform", "linux"):
        backend = default_backend()
    assert backend.requires_preparation
    assert backend.targets() == []
