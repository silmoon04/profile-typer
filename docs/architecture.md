# Architecture

The desktop UI has no runtime dependency on an activity collector or database.
The source distribution includes the author's validated aggregate typing profile.

| Module | Responsibility |
| --- | --- |
| `typing_document.py` | Queue identities, edits, selection, locking, and atomic JSON saves. |
| `view_schema.py` | Validated custom views, rows, fields, options, colors, and legacy-format compatibility. |
| `typing_session.py` | Permission preparation, countdown, worker lifetime, progress, cancellation, completion, and failure. |
| `engine.py` | Shared recorded-cadence replay with interruptible waits. Accepts an input port, random generator, and clock. |
| `profiles.py`, `data/silmoon04.json` | Bundled recording aggregates and schema validation. Missing or invalid data fails visibly instead of selecting generic timing. |
| `cadence.py` | The original simulator's empirical sampler and correction planner, extracted without its tracker or GUI dependencies. |
| `typing_backends.py` | Desktop detection and backend selection. |
| `platforms/windows.py` | Windows input adapter using the local Win32 implementation. |
| `platforms/x11.py` | X11 window discovery, focus checks, Escape, and `xdotool` delivery. |
| `platforms/wayland.py` | Permission-based keyboard delivery through the desktop portal. |
| `qt_typer/` | Qt list model, views, dialogs, and window placement. |
| `qt_typer/theme.py`, `assets/theme.qss` | Shared fonts, colors, control styling, and application icon. |

Custom views use the same document and typing session as simple queues. A field
Type action passes a snapshot of that field's value to the session. The document
owns usage counters and blocks edits while typing; view navigation cannot redirect
an active run. Copy counters count accepted clipboard actions and type counters
count accepted starts. Status is kept separately so cancellation is not completion.

The renderer uses Qt text widgets and validated colors. It does not embed a web
browser or run HTML. Rows reflow within the available width, and text editors
grow with their contents so the outer view owns vertical scrolling. The optional
answer-guide converter reads a JSON data block without executing page scripts.

The view editor caches four inactive views to preserve cursor, selection, and
undo state during navigation. It rebuilds cards when their layout metadata
changes and reads answer values from the document. Rows constrain their column
count using the scroll viewport width, independently of old layout minimums.
Field action buttons have their parent assigned before visibility is set;
startup and smoke tests reject unintended top-level show events.

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

The Windows build uses PyInstaller in windowed, one-folder mode. It includes
Python, Qt, fonts, and profile data, plus license notices. The packaged
executable exposes the same smoke check with `--check OUTPUT`.
