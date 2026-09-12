"""Build a portable Windows app with its own Python and Qt runtime."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from importlib.metadata import distribution
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-archive", action="store_true", help="build the app folder only")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Build the Windows executable on Windows.")
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    destination = root / "dist/windows" / version
    environment = dict(os.environ, PYTHONPATH=str(root / "src"))
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed", "--noupx",
        "--name", "ProfileTyper", "--paths", str(root / "src"),
        "--distpath", str(destination), "--workpath", str(root / "build/windows"),
        "--specpath", str(root / "build"), "--collect-data", "profile_typer",
        "--icon", str(root / "src/profile_typer/assets/profile-typer.ico"),
        "--exclude-module", "tkinter", "--exclude-module", "PyQt5", "--exclude-module", "PyQt6",
        str(root / "packaging/windows_entry.py"),
    ], check=True, cwd=root, env=environment)
    app = destination / "ProfileTyper"
    for name in ("LICENSE", "README.md"):
        shutil.copy2(root / name, app / name)
    shutil.copy2(root / "packaging/THIRD_PARTY_NOTICES.txt", app / "THIRD_PARTY_NOTICES.txt")
    shutil.copytree(root / "packaging/licenses", app / "licenses", dirs_exist_ok=True)
    installer = distribution("pyinstaller")
    for relative in installer.files:
        if "license" in str(relative).lower() or relative.name.lower().startswith("copying"):
            source = Path(installer.locate_file(relative))
            if source.is_file():
                target = app / "licenses/PyInstaller" / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    if not args.no_archive:
        archive = root / "dist" / f"ProfileTyper-{version}-windows-x64"
        shutil.make_archive(str(archive), "zip", destination, "ProfileTyper")
        print(str(archive) + ".zip")
    print(app / "ProfileTyper.exe")


if __name__ == "__main__":
    main()
