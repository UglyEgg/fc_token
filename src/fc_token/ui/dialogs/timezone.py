from __future__ import annotations

from zoneinfo import available_timezones

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from fc_token.config import DEFAULT_TIMEZONE
from fc_token.timezone_utils import resolve_local_timezone

# Cache the full timezone list once at import time to avoid repeated
# calls to available_timezones() each time the dialog is opened.
ALL_TIMEZONES = sorted(available_timezones())


def run_timezone_dialog(parent: QWidget | None = None) -> str | None:
    """Show a simple timezone selection dialog.

    Returns the selected timezone name (IANA string) or None if cancelled.
    """
    resolved_tz = resolve_local_timezone(DEFAULT_TIMEZONE)
    current_tz_name = resolved_tz.display_name
    current_tz_key = resolved_tz.canonical_name or DEFAULT_TIMEZONE

    # Use the cached global list
    all_tzs = ALL_TIMEZONES

    dlg = QDialog(parent)
    dlg.setWindowTitle("Set timezone")
    layout = QVBoxLayout(dlg)

    label = QLabel(f"Current timezone: {current_tz_name}", dlg)
    layout.addWidget(label)

    combo = QComboBox(dlg)
    combo.addItems(all_tzs)

    # Preselect current tz if present
    try:
        idx = all_tzs.index(current_tz_key)
    except ValueError:
        idx = -1

    if idx >= 0:
        combo.setCurrentIndex(idx)

    layout.addWidget(combo)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        parent=dlg,
    )
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    return combo.currentText()
