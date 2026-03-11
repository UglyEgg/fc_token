from __future__ import annotations

import os
from datetime import timezone, tzinfo
from zoneinfo import ZoneInfo

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont, QTextOption
from PyQt6.QtWidgets import QTextEdit, QWidget

from fc_token.config import SETTINGS_ORG, SETTINGS_APP, KEY_TIMEZONE


def make_code_view(parent: QWidget | None = None) -> QTextEdit:
    """Create a read-only, monospaced, soft-wrapped code viewer."""
    text = QTextEdit(parent)
    text.setReadOnly(True)
    text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    text.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)

    code_font = QFont()
    code_font.setFamily("Monospace")
    text.setFont(code_font)
    return text


def get_local_zone_name(default_tz_name: str) -> str:
    """Return the effective timezone name used by the app.

    Priority:
        1. User-selected timezone stored in QSettings.
        2. TIMEZONE environment variable.
        3. Provided default_tz_name (usually DEFAULT_TIMEZONE).
    """
    tz_name: str | None = None

    try:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        value = settings.value(KEY_TIMEZONE, "", type=str)
        if value:
            tz_name = value
    except Exception:
        tz_name = None

    if not tz_name:
        tz_name = os.environ.get("TIMEZONE") or default_tz_name

    return tz_name


def get_local_zone(default_tz_name: str) -> tzinfo:
    """Return a tzinfo for the effective timezone.

    Falls back to UTC if the named timezone is not available.
    """
    tz_name = get_local_zone_name(default_tz_name)
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return timezone.utc
