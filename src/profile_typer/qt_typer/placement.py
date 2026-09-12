"""Place a desktop window inside a connected monitor's usable area."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication


def _fit(window, screen, *, center):
    area = screen.availableGeometry().adjusted(16, 16, -16, -16)
    frame = window.frameGeometry()
    extra_width = max(0, frame.width() - window.width())
    extra_height = max(0, frame.height() - window.height())
    window.resize(min(window.width(), area.width() - extra_width),
                  min(window.height(), area.height() - extra_height))
    width = window.width() + extra_width
    height = window.height() + extra_height
    if center:
        position = QPoint(area.x() + (area.width() - width) // 2, area.y() + (area.height() - height) // 2)
    else:
        position = QPoint(max(area.left(), min(frame.x(), area.right() - width + 1)),
                          max(area.top(), min(frame.y(), area.bottom() - height + 1)))
    window.move(position)


def show_on_screen(window, screen=None):
    app = QApplication.instance()
    screen = screen or app.screenAt(QCursor.pos()) or app.primaryScreen()
    window.setScreen(screen)
    _fit(window, screen, center=True)
    window.showNormal()
    if app.platformName() == "windows":
        import ctypes
        from ctypes import wintypes
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        for attribute, color in ((35, 0x001f2320), (36, 0x00e9f2f4)):
            value = wintypes.DWORD(color)
            setter(int(window.winId()), attribute, ctypes.byref(value), ctypes.sizeof(value))
    _fit(window, screen, center=True)
    window.raise_()
    window.activateWindow()

    def check_native_frame():
        if window.isVisible() and not any(display.availableGeometry().contains(window.frameGeometry()) for display in app.screens()):
            _fit(window, window.screen(), center=False)

    # The native title bar dimensions become available after the window is shown.
    QTimer.singleShot(0, window, check_native_frame)
