# Windows app

Download `ProfileTyper-0.4.0-windows-x64.zip` from the releases page. Extract the
whole folder, then double-click **ProfileTyper.exe**. Python is included. Keep
the `_internal` folder beside the executable; it contains Qt, the fonts, and
the recorded typing profile.

Use Open or Paste JSON inside the app. You can also drag a JSON file onto the
executable, or pass its path as the first command-line argument. Create a
shortcut to the executable wherever you usually launch applications.

The build has an app icon and uses the Windows GUI subsystem, so launching it
does not open a terminal. This release is unsigned.

## Build from source

Use a dedicated environment on Windows with Python 3.12:

```powershell
python -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install '.[dev]' PySide6-Essentials==6.9.3 PyInstaller==6.22.2 pillow
.\.build-venv\Scripts\python.exe scripts/build_windows.py
```

The output is a folder in `dist/windows/0.4.0/ProfileTyper` and a ZIP in `dist`.
The build includes notices and license texts. Dependencies remain separate
shared libraries. `scripts/build_icons.py` regenerates PNG and ICO files from
the SVG masters when the icon changes.

## Check the packaged app

```powershell
.\dist\windows\0.4.0\ProfileTyper\ProfileTyper.exe --check C:\Temp\profile-typer-check
```

This writes a result JSON and screenshots, using preview delivery. Add
`--check-native` to show the test window during the run. The test deliberately
resizes that one window and checks that no field buttons open their own windows.

For manual preview, launch with `--dry-run --no-settings`. Preview uses the
recorded timing model but sends no keys to another application.
