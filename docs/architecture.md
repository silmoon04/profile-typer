# Architecture

The desktop UI has no runtime dependency on an activity collector or database.
The source distribution includes the author's validated aggregate typing profile.

| Module | Responsibility |
| --- | --- |
| `typing_document.py` | Queue identities, edits, selection, locking, and atomic JSON saves. |
| `typing_session.py` | Permission preparation, countdown, worker lifetime, progress, cancellation, completion, and failure. |
| `engine.py` | Shared recorded-cadence replay with interruptible waits. Accepts an input port, random generator, and clock. |
| `profiles.py`, `data/silmoon04.json` | Bundled recording aggregates and schema validation. Missing or invalid data fails visibly instead of selecting generic timing. |
| `cadence.py` | The original simulator's empirical sampler and correction planner, extracted without its tracker or GUI dependencies. |
| `typing_backends.py` | Desktop detection and backend selection. |
| `platforms/windows.py` | Windows input adapter using the local Win32 implementation. |
| `platforms/x11.py` | X11 window discovery, focus checks, Escape, and `xdotool` delivery. |
| `platforms/wayland.py` | Permission-based keyboard delivery through the desktop portal. |
| `qt_typer/` | Qt list model, views, dialogs, and window placement. |

The UI and worker communicate through queued events. Workers never access Qt
widgets. Documents remain locked until the worker exits. Successful completion
may select the next item; cancellation or failure never advances the queue.

The planner validates the entire correction sequence before input begins. It
must reconstruct the supplied description exactly. Timing selects recorded
key-pair, category-pair, key, category, or global distributions, with the
original sample-count weighting and conditional rhythm blend. Every platform
uses this same planner, sampler, and bundled data.

Platform modules load only after the active desktop is identified. Importing
the package on Linux does not load Win32 libraries. Preview delivery uses the
same engine with an in-memory port and sends no keystrokes. Automated UI checks
explicitly accelerate its clock; ordinary preview runs keep the chosen pace.

On Wayland, a preparation worker asks the portal for keyboard access. The
countdown starts only after approval. The connection remains on a dedicated
asyncio loop, and the session is closed on completion or cancellation. No
screen capture, pointer access, privileged device daemon, or stored permission
token is requested.

The wheel and `.deb` package share the same source. The `.deb` launcher imports
the installed package using Debian's Python, and dependency resolution is left
to apt. Tests exercise the same document and session interfaces as the UI.
