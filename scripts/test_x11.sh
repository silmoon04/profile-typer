#!/bin/sh
set -eu
export QT_QPA_PLATFORM=xcb
export XDG_SESSION_TYPE=x11
export PROFILE_TYPER_TEST_X11=1
unset WAYLAND_DISPLAY
openbox > /tmp/profile-typer-openbox.log 2>&1 &
manager=$!
trap 'kill "$manager" 2>/dev/null || true' EXIT
sleep 1
python3 -m pytest -q tests/test_x11_delivery.py
