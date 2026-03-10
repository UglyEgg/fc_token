from __future__ import annotations

from PyQt6.QtGui import QFont, QTextOption
from PyQt6.QtWidgets import QTextEdit, QWidget


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
