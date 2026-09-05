# Verification status

This page separates checks of the package from desktop-specific input tests.
The GitHub Actions workflow is included, but hosted jobs did not execute for
the first release. The verification results below were obtained locally.

## Verified locally

- Windows: Python 3.12, PySide6 6.9.1; unit and offscreen Qt tests, plus an
  installed wheel's smoke command run from outside the checkout.
- Debian 13.6: Python 3.13.5, Debian's PySide6 6.8.2.1; the same unit and UI tests.
- X11: real XTEST input into a separate Qt process inside Xvfb with Openbox.
  The received text matches accents, emoji, tabs, multiple lines, and trailing
  blank lines exactly. Cancellation stops before remaining characters.
- The `.deb` builds without root, installs with apt, and its installed smoke
  command runs from outside the source tree with `PYTHONPATH` removed.
- The wheel and source archive build successfully. Screenshots cover wide,
  side, compact, queue, and settings views.
- The Wayland client is exercised against a private D-Bus portal fixture:
  permission ordering, keyboard-only selection, key-down/key-up pairs, session
  closure, and permission denial without sending any keys.

## Wayland limitation

The portal protocol tests do **not** verify GNOME or KDE's real permission
dialog and compositor delivery. That desktop integration remains experimental
until tested in an interactive Wayland session. A desktop without the
RemoteDesktop portal gets an actionable error instead of silently falling back
to X11 or using a privileged input daemon.

Use a Debian X11 session for the currently verified automatic typing path.
The UI and preview mode also work without permission to inject input.

## Reproduce

Normal unit and UI checks:

```sh
python -m pytest -q
python -m ruff check src tests scripts
profile-typer-check --output artifacts/smoke
```

In a disposable Debian environment with the dependencies from the CI workflow:

```sh
sh scripts/test_debian.sh
```

That script installs the built `.deb`, so run it as root only in the disposable
test environment. For just the isolated desktop fixtures:

```sh
PYTHONPATH=src xvfb-run -a dbus-run-session -- sh scripts/test_x11.sh
PYTHONPATH=src PROFILE_TYPER_TEST_PORTAL=1 dbus-run-session -- python3 -m pytest -q tests/test_portal_protocol.py
```

Do not enable the portal fixture on your normal session bus: it deliberately
registers a fake desktop portal. The `dbus-run-session` command isolates it.
The X11 fixture opens only a temporary text receiver on its private display.
