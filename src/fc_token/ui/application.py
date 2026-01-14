# fc_token/ui/application.py

from __future__ import annotations

import sys
from typing import Sequence

from PyQt6.QtWidgets import QApplication

from fc_token.cache import CodeCache
from fc_token.config import APP_NAME, APP_VERSION
from fc_token.icons import load_app_icon
from fc_token.ui.main_window import MainWindow
from fc_token.ui.tray import TrayController


def main(argv: Sequence[str] | None = None) -> int:
    """Application entry point.

    Refactored to honour the "open main window on start" preference stored
    in QSettings (via TrayController.open_on_start), while keeping the
    ``--version`` and ``--self-test`` behaviours intact.
    """
    if argv is None:
        argv = sys.argv

    # Simple CLI flags before Qt starts
    if "--version" in argv or "-V" in argv:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0

    # Lightweight self-test path: create the app, main window, and tray,
    # run a single initial load, then exit without entering the full event loop.
    if "--self-test" in argv:
        try:
            app = QApplication(list(argv))
            app.setQuitOnLastWindowClosed(False)

            app_icon = load_app_icon()
            if not app_icon.isNull():
                app.setWindowIcon(app_icon)

            app.setDesktopFileName("fc_token")

            cache = CodeCache()
            win = MainWindow(cache)
            tray = TrayController(win, cache)
            win.set_tray_controller(tray)

            # For self-test, we don't need to show the main window.
            win.hide()
            tray.initial_load(use_network=False)
            return 0
        except Exception as e:  # pragma: no cover - defensive
            print(f"fc-token self-test failed: {e}", file=sys.stderr)
            return 1

    # Normal GUI run
    app = QApplication(list(argv))
    app.setQuitOnLastWindowClosed(False)

    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    app.setDesktopFileName("fc_token")

    cache = CodeCache()
    win = MainWindow(cache)
    tray = TrayController(win, cache)
    win.set_tray_controller(tray)

    # Honour the user's "open main window on start" preference.
    if tray.open_on_start:
        win.show()
    else:
        win.hide()

    tray.initial_load()

    return app.exec()
