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
    """Application entry point."""
    if argv is None:
        argv = sys.argv

    # Simple CLI flags before Qt starts
    if "--version" in argv or "-V" in argv:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0

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

            # Self-test is a headless smoke test; keep the window hidden.
            win.hide()
            tray.initial_load()
            return 0
        except Exception as e:
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

    # Respect the "Open main window on start" setting.
    # Default: True (show window if setting doesn't exist yet).
    if getattr(tray, "open_on_start", True):
        win.show()
    else:
        win.hide()

    tray.initial_load()

    return app.exec()
