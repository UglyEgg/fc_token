"""KDE/Plasma-friendly tray application for File Centipede activation codes.

This module now delegates to the modular UI package:

    fc_token.ui.application:main
"""

from __future__ import annotations

from fc_token.ui.application import main

if __name__ == "__main__":
    raise SystemExit(main())
