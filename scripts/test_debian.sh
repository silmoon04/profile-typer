#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
project=$PWD
unset XDG_RUNTIME_DIR WAYLAND_DISPLAY
export PYTHONPATH="$PWD/src"
python3 -c 'import platform, PySide6; print(platform.freedesktop_os_release()); print("PySide", PySide6.__version__)'
python3 -m pytest -q
xvfb-run -a dbus-run-session -- sh scripts/test_x11.sh
PROFILE_TYPER_TEST_PORTAL=1 dbus-run-session -- python3 -m pytest -q tests/test_portal_protocol.py
python3 -m profile_typer.smoke --output artifacts/debian-smoke
python3 -m build --no-isolation
python3 scripts/build_deb.py
version=$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
apt-get install -y -qq --reinstall --no-install-recommends "./dist/profile-typer_${version}_all.deb"
cd /tmp
env -u PYTHONPATH python3 -c 'from profile_typer.profiles import recorded_profile; p=recorded_profile(); assert p.id=="silmoon04-v1"; assert p.timing["summary"]["interval_samples"]==337035; print("Installed recorded profile:", p.id, p.timing["summary"])'
env -u PYTHONPATH QT_QPA_PLATFORM=offscreen profile-typer-check --output "$project/artifacts/installed-debian-smoke"
