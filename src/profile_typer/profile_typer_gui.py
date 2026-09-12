"""Launch the Qt profile typer: python -m profile_typer.profile_typer_gui."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Type descriptions from an editable JSON queue.")
    parser.add_argument("--version", action="version", version=f"Profile Typer {__version__}")
    parser.add_argument("queue", nargs="?", type=Path, help="JSON file to open")
    parser.add_argument("--dry-run", action="store_true", help="preview typing without sending any keystrokes")
    parser.add_argument("--no-settings", action="store_true", help="use defaults without reading or saving preferences")
    args = parser.parse_args(argv)
    try:
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from .qt_typer.window import TyperWindow, configure_application
        from .qt_typer.placement import show_on_screen
    except ImportError as error:
        print(f"Cannot load the Qt UI: {error}\nInstall the wheel with pip or the Debian package with apt.", file=sys.stderr)
        return 2
    from .typing_backends import PreviewTypingBackend, default_backend
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Profile Typer")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("io.github.silmoon04.ProfileTyper")
    configure_application(app)
    window = TyperWindow(backend=PreviewTypingBackend() if args.dry_run else default_backend(),
                         preferences=None if args.no_settings else QSettings("ProfileTyper", "ProfileTyper"))
    show_on_screen(window)
    if args.queue:
        window.open_json(path=args.queue)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
