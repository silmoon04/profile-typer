# Architecture

The desktop UI has no dependency on an activity collector, a database, or a
recorded typing profile. The source distribution contains only this app.

| Module | Responsibility |
| --- | --- |
| `typing_document.py` | Queue identities, edits, selection, locking, and atomic JSON saves. |
| `typing_session.py` | Permission preparation, countdown, worker lifetime, progress, cancellation, completion, and failure. |
| `engine.py` | Portable replay with generic timing and optional corrections. Accepts an input port and clock. |
| `typing_backends.py` | Desktop detection and backend selection. |
| `platforms/windows.py` | Windows input adapter using the local Win32 implementation. |
| `platforms/x11.py` | X11 window discovery, focus checks, Escape, and `xdotool` delivery. |
| `platforms/wayland.py` | Permission-based keyboard delivery through the desktop portal. |
| `qt_typer/` | Qt list model, views, dialogs, and window placement. |

The UI and worker communicate through queued events. Workers never access Qt
widgets. Documents remain locked until the worker exits. Successful completion
may select the next item; cancellation or failure never advances the queue.

Platform modules load only after the active desktop is identified. Importing
the package on Linux does not load Win32 libraries. Preview delivery has no
platform dependencies and sends no keystrokes.

On Wayland, a preparation worker asks the portal for keyboard access. The
countdown starts only after approval. The connection remains on a dedicated
asyncio loop, and the session is closed on completion or cancellation. No
screen capture, pointer access, privileged device daemon, or stored permission
token is requested.

The wheel and `.deb` package share the same source. The `.deb` launcher imports
the installed package using Debian's Python, and dependency resolution is left
to apt. Tests exercise the same document and session interfaces as the UI.
