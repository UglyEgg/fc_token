from __future__ import annotations

from datetime import tzinfo
from typing import Sequence

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fc_token.models import CodeEntry
from fc_token.ui.utils import make_code_view


def show_future_codes_dialog(
    parent: QWidget,
    codes: Sequence[CodeEntry],
    local_zone: tzinfo,
) -> None:
    """Show a popup listing future activation codes and allow inspecting one."""
    if not codes:
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.information(
            parent,
            "Future codes",
            "There are no cached activation codes to display.",
        )
        return

    dialog = QDialog(parent)
    dialog.setWindowTitle("Future activation codes")
    layout = QVBoxLayout(dialog)

    table = QTableWidget(dialog)
    table.setColumnCount(2)
    table.setHorizontalHeaderLabels(["Start", "End"])
    table.setRowCount(len(codes))
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    for row, entry in enumerate(codes):
        start_local = entry.start.astimezone(local_zone)
        end_local = entry.end.astimezone(local_zone)
        start_str = start_local.strftime("%Y-%m-%d %H:%M")
        end_str = end_local.strftime("%Y-%m-%d %H:%M")

        table.setItem(row, 0, QTableWidgetItem(start_str))
        table.setItem(row, 1, QTableWidgetItem(end_str))

    header: QHeaderView = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    layout.addWidget(table)

    def open_entry(row: int, _column: int) -> None:
        if row < 0 or row >= len(codes):
            return
        entry = codes[row]

        dlg2 = QDialog(dialog)
        dlg2.setWindowTitle("Activation code")
        v = QVBoxLayout(dlg2)

        # Use the same compact code view as the main window
        text: QTextEdit = make_code_view(dlg2)
        text.setPlainText(entry.code)
        # Match requested tighter height
        text.setFixedHeight(122)
        v.addWidget(text)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.accepted.connect(dlg2.accept)
        btns.rejected.connect(dlg2.reject)
        v.addWidget(btns)

        # Make the dialog hug its content and not be taller than needed
        dlg2.adjustSize()
        dlg2.setFixedSize(dlg2.sizeHint())

        dlg2.exec()

    # Double-click to open detail, to avoid accidental opening on single click.
    table.cellDoubleClicked.connect(open_entry)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=dialog)
    button_box.accepted.connect(dialog.accept)
    layout.addWidget(button_box)

    dialog.exec()
