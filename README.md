# Profile Typer

A desktop queue for typing descriptions into other applications. Import a JSON
file or paste JSON, browse items by title, edit their descriptions, and send the
selected description at a chosen pace.

The app ships **silmoon04's recorded typing profile**: key-pair timing, hold
times, burst/pause patterns, word-specific mistakes, and backspace corrections.
Every platform loads the same bundled aggregate profile.

The app uses Python and Qt Widgets. It includes search, Back/Next navigation,
queue editing, a countdown, precise WPM controls, cancellation, and a preview
mode that never sends input to another application.

## Install

### Debian 13

Download the `.deb` from the [releases page](https://github.com/silmoon04/profile-typer/releases), then install it:

```sh
sudo apt install ./profile-typer_0.3.0_all.deb
profile-typer
```

The package uses Debian's Qt and Python libraries. It also installs a desktop
launcher. X11 input uses `xdotool`; Wayland input uses the desktop's
RemoteDesktop permission portal.

### Windows or a Python virtual environment

Install the wheel from the releases page with Python 3.11 or newer:

```sh
python -m pip install ./profile_typer-0.3.0-py3-none-any.whl
profile-typer
```

For a source checkout:

```sh
git clone https://github.com/silmoon04/profile-typer.git
cd profile-typer
python -m venv .venv
# Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
python -m profile_typer
```

On Linux, the pip installation also needs system Qt runtime libraries and
`xdotool` for X11. Debian 13 users should prefer the `.deb` installation.

## Use a queue

```json
[
  {"title": "hello", "description": "text to type out"},
  {"title": "Two paragraphs", "description": "First paragraph.\n\nSecond paragraph."}
]
```

Choose **Open** for a file or **Paste JSON** to paste an object or array. Both
`title` and `description` must be strings. Only the description is typed.
Paste can replace or append to the queue, and invalid input leaves existing
items intact. Save exports the edited titles and descriptions.

For a workflow with several answers per step, use **custom views**. A view can
group editable text fields, reference values, and selected options into rows.
Each field has Copy/Type actions and separate clipboard/pencil counters. Rows
adapt to smaller windows, and the view scrolls only when its content needs it.
Typing one field stays in that view so other fields are not skipped.

See the [custom view guide](docs/custom-views.md) and
[example JSON](src/profile_typer/examples/views.json). Existing title/description
queues continue to work. Saved view files include edits, choices, counters, and
statuses; copying and typing do not save your answers in the background.

WPM, delay, corrections, and variation are on the main page. Defaults use the
recorded profile: **81.6 WPM reference pace, corrections 1×, variation 100%**.
WPM rescales the measured intervals; net WPM varies with bursts and correction
pauses. Corrections can backtrack through a word, with measured delays before
deleting and resuming. Set corrections to 0 to disable them explicitly.
See [the bundled profile](docs/recorded-profile.md) for its data and behavior.

Version 0.1.0 incorrectly replaced the recorded model with generic timing and
disabled corrections. Upgrading to 0.2.0 resets those old model defaults once,
while preserving the start delay and advance option. Later changes, including
explicitly disabling corrections, are remembered. **More > Use recorded profile
defaults** restores the measured defaults at any time.

Windows open within a connected display, and narrow layouts keep the typing
controls visible. The profile name is visible below the description and its
sample counts are shown in Settings and Diagnostics.

Select a destination, click **Type description**, and focus the exact input
field during the countdown. Each queue item starts manually. A stopped item
restarts from the beginning, so clear partial output before starting it again.
Enter and Tab are real key presses: their effects depend on the destination.

```sh
profile-typer --dry-run --no-settings
profile-typer path/to/queue.json
```

Preview also runs the recorded timing and correction engine, without sending
keys to another application. Preview output is available under **More > Preview output**. Diagnostics show
the selected backend, settings, transitions, and the last error traceback.

## Desktop support

| Desktop | Delivery | Cancellation and limits |
| --- | --- | --- |
| Windows | Unicode `SendInput`; exact window selection | Escape, Stop, or foreground-window changes. Elevated targets may reject input. |
| Debian X11 | XTEST through `xdotool`; exact window selection | Escape, Stop, or foreground-window changes. Requires an X11 session and a window manager. |
| Wayland with RemoteDesktop portal | Keyboard permission requested from the desktop before the countdown | Stop or the desktop sharing indicator. No global window enumeration or focus-change detection. |
| Preview | In-memory text only | Works without a desktop input backend. |

Wayland support depends on the installed portal backend. GNOME and KDE expose
the relevant interface; other compositors may not. The app minimizes after
permission so you can focus the destination, and returns when the run finishes.
Wayland's global Escape handling and window selection are not available here.
See [verification status](docs/verification.md) for exactly what was tested.

## Development and checks

```sh
python -m pytest
python -m ruff check src tests scripts
profile-typer-check --output artifacts/smoke
python -m build
python scripts/build_deb.py             # Debian/Linux with dpkg-deb installed
```

The UI suite uses Qt's offscreen platform. The smoke check saves screenshots
and a JSON result. Linux CI also uses a private Xvfb display for actual text
delivery and a private D-Bus session for portal lifecycle checks. Run live
desktop tests only in the isolated fixtures described in
[verification status](docs/verification.md).

The [architecture guide](docs/architecture.md) describes the document, session,
engine, and platform adapters. The app does not capture background activity or
upload text. Queue files are written only when explicitly saved; preferences
use the operating system's normal Qt settings store.

## License

MIT. Qt/PySide and other dependencies retain their own licenses. The Debian
package uses system dependencies rather than embedding their binaries.
