from __future__ import annotations

from typing import Tuple

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def run_refresh_interval_dialog(
    parent: QWidget,
    current_interval_minutes: int,
    interval_auto_enabled: bool,
) -> tuple[int, bool] | None:
    """Show the refresh interval dialog.

    Returns:
        (new_interval_minutes, interval_auto_enabled) on OK,
        or None if the user cancels.
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle("Set refresh interval")
    lay = QVBoxLayout(dlg)

    auto_cb = QCheckBox("Automatically schedule based on code expiry")
    auto_cb.setChecked(interval_auto_enabled)
    lay.addWidget(auto_cb)

    total = current_interval_minutes
    days = total // (60 * 24)
    hours = (total // 60) % 24

    # Days
    row_days = QHBoxLayout()
    lbl_days = QLabel("Days:")
    spin_days = QSpinBox()
    spin_days.setRange(0, 365)
    spin_days.setValue(days)
    row_days.addWidget(lbl_days)
    row_days.addWidget(spin_days)
    lay.addLayout(row_days)

    # Hours
    row_hours = QHBoxLayout()
    lbl_hours = QLabel("Hours:")
    spin_hours = QSpinBox()
    spin_hours.setRange(0, 23)
    spin_hours.setValue(hours)
    row_hours.addWidget(lbl_hours)
    row_hours.addWidget(spin_hours)
    lay.addLayout(row_hours)

    def update_enabled(state: bool) -> None:
        enabled = not state
        spin_days.setEnabled(enabled)
        spin_hours.setEnabled(enabled)

    update_enabled(auto_cb.isChecked())
    auto_cb.toggled.connect(update_enabled)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    auto_enabled = auto_cb.isChecked()
    if auto_enabled:
        # The actual interval will be computed based on code expiry.
        return current_interval_minutes, True

    total_minutes = spin_days.value() * 24 * 60 + spin_hours.value() * 60
    if total_minutes < 1:
        total_minutes = 1

    return total_minutes, False
