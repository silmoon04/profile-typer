"""Reproducible GUI checks and screenshots using preview delivery only."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the Qt typer without sending text to other applications.")
    parser.add_argument("--output", type=Path, required=True, help="directory for screenshots and the result JSON")
    parser.add_argument("--native", action="store_true", help="show the test window on the desktop")
    parser.add_argument("--snap", action="store_true", help="also exercise Windows+Left on the test window; requires --native")
    args = parser.parse_args(argv)
    if args.snap and (not args.native or os.name != "nt"):
        parser.error("--snap requires --native on Windows")
    if args.native:
        os.environ.pop("QT_QPA_PLATFORM", None)
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    import PySide6
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from profile_typer.qt_typer.window import TyperWindow, configure_application
    from profile_typer.typing_backends import PreviewTypingBackend
    from profile_typer.typing_document import TypingDocument
    from profile_typer.typing_session import Phase

    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    configure_application(app)
    document = TypingDocument()
    document.load(Path(__file__).resolve().parent / "examples" / "typing-queue.json")
    backend = PreviewTypingBackend()
    window = TyperWindow(document=document, backend=backend)
    window.show()
    measurements = []

    def check(name, page):
        app.processEvents()
        QTest.qWait(60)
        widgets = [window.start_button, window.stop_button, window.target_combo, window.paste_button, *window.spins.values()]
        if page == 0:
            widgets.extend([window.description_edit, window.back_button, window.next_button])
            assert window.description_edit.height() >= 70
        if page == 1:
            widgets.extend([window.list_view, window.up_button, window.down_button])
        for widget in widgets:
            assert widget.isVisible(), f"{name}: {type(widget).__name__} hidden"
            point = widget.mapTo(window, QPoint(0, 0))
            assert point.x() >= 0 and point.y() >= 0
            assert point.x() + widget.width() <= window.width(), f"{name}: horizontal clipping"
            assert point.y() + widget.height() <= window.height(), f"{name}: vertical clipping"
        assert window.grab().save(str(args.output / f"{name}.png"))
        measurements.append({"name": name, "width": window.width(), "height": window.height(),
                             "device_pixel_ratio": window.devicePixelRatioF(), "controls_visible": True})

    try:
        for name, width, height, page in (("wide", 1000, 720, 0), ("side", 638, 720, 0),
                                           ("compact", 380, 420, 0), ("queue", 380, 420, 1),
                                           ("settings", 360, 400, 2)):
            window.resize(width, height)
            app.processEvents()
            window.tabs.setCurrentIndex(page)
            check(name, page)
        window.tabs.setCurrentIndex(0)
        window.spins["delay"].setValue(0)
        expected = document.selected.description
        QTest.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
        deadline = time.monotonic() + 5
        while window.session.busy and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert window.session.phase == Phase.DONE, window.session.message
        assert backend.output == expected
        assert document.selected_index == 1
        check("preview-complete", 0)
        if args.snap:
            from profile_typer.platforms.win32_input import _user32, ensure_modifiers_released, focus_window
            window.resize(1000, 720)
            app.processEvents()
            focus_window(int(window.winId()))
            ensure_modifiers_released()
            user32 = _user32()
            user32.keybd_event(0x5B, 0, 0, 0)
            try:
                user32.keybd_event(0x25, 0, 1, 0)
                user32.keybd_event(0x25, 0, 3, 0)
            finally:
                user32.keybd_event(0x5B, 0, 2, 0)
            QTest.qWait(800)
            app.processEvents()
            available = window.screen().availableGeometry()
            assert window.width() <= available.width() / 2 + 20, "Windows snap did not reduce the width"
            check("windows-snap", 0)
        report = {"passed": True, "qt_version": PySide6.__version__, "preview_exact_match": True,
                  "cases": measurements, "state_history": list(window.session.history)}
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
    finally:
        window.session.stop()
        deadline = time.monotonic() + 3
        while window.session.busy and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        document.dirty = False
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
