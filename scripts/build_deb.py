"""Build a Debian 13 package without root or bundled third-party binaries."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if not shutil.which("dpkg-deb"):
        parser.error("dpkg-deb is required; build this package on Debian or another Debian-based system")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="profile-typer-deb-") as directory:
        stage = Path(directory)
        package = stage / "usr/lib/python3/dist-packages/profile_typer"
        shutil.copytree(root / "src/profile_typer", package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for command, module in (("profile-typer", "profile_typer_gui"), ("profile-typer-check", "smoke")):
            launcher = stage / "usr/bin" / command
            launcher.parent.mkdir(parents=True, exist_ok=True)
            launcher.write_text(f"#!/usr/bin/python3\nfrom profile_typer.{module} import main\nraise SystemExit(main())\n")
            launcher.chmod(0o755)
        for source, destination in (("packaging/io.github.silmoon04.ProfileTyper.desktop", "usr/share/applications/io.github.silmoon04.ProfileTyper.desktop"),
                                    ("src/profile_typer/assets/profile-typer.svg", "usr/share/icons/hicolor/scalable/apps/profile-typer.svg"),
                                    ("LICENSE", "usr/share/doc/profile-typer/copyright"),
                                    ("README.md", "usr/share/doc/profile-typer/README.md")):
            target = stage / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / source, target)
        control = stage / "DEBIAN/control"
        control.parent.mkdir()
        control.write_text(f"""Package: profile-typer
Version: {version}
Architecture: all
Section: utils
Priority: optional
Maintainer: Profile Typer contributors <silmoon04@users.noreply.github.com>
Depends: python3 (>= 3.11), python3-pyside6.qtwidgets (>= 6.8), python3-pyside6.qttest, python3-xlib, python3-dbus-next, qt6-wayland, xdotool, fonts-dejavu-core
Recommends: xdg-desktop-portal
Suggests: xdg-desktop-portal-gnome | xdg-desktop-portal-kde
Homepage: https://github.com/silmoon04/profile-typer
Description: Desktop queue for typing JSON descriptions
 Import or paste JSON, edit and browse descriptions, and type them into
 another application. Includes a preview mode and desktop-specific input.
""")
        # Windows-mounted source trees may report mode 0777; never ship that into /usr.
        stage.chmod(0o755)
        for path in stage.rglob("*"):
            executable = path.parent == stage / "usr/bin"
            path.chmod(0o755 if path.is_dir() or executable else 0o644)
        environment = dict(os.environ)
        environment.setdefault("SOURCE_DATE_EPOCH", "1788566400")
        target = output / f"profile-typer_{version}_all.deb"
        subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(stage), str(target)], check=True, env=environment)
        print(target)


if __name__ == "__main__":
    main()
