"""Icon and theme helpers for fc-token."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QApplication


PKG_ROOT = Path(__file__).resolve().parent


def resource_path(filename: str) -> Optional[str]:
    """Return an absolute path to a resource file inside the package."""
    # Dev / editable install: src/fc_token/resources
    fallback = PKG_ROOT / "resources" / filename
    if fallback.exists():
        return str(fallback)
    return None


def load_app_icon() -> QIcon:
    """Load the window/app icon.

    Preference order:
    1. Icon theme name 'fc_token'
    2. Packaged resource 'fc_token.png'
    3. Fallback: empty QIcon()
    """
    icon = QIcon.fromTheme("fc_token")
    if not icon.isNull():
        return icon

    path = resource_path("fc_token.png")
    if path:
        icon = QIcon(path)
        if not icon.isNull():
            return icon

    return QIcon()


def load_tray_base_icon() -> QIcon:
    """Load the base tray icon (monochrome duck).

    Preference order:
    1. Icon theme 'fc_token-symbolic'
    2. Icon theme 'fc_token'
    3. Packaged resource 'fc_token_symbolic.svg'
    4. Fallback: app icon
    """
    icon = QIcon.fromTheme("fc_token-symbolic")
    if not icon.isNull():
        return icon

    icon = QIcon.fromTheme("fc_token")
    if not icon.isNull():
        return icon

    path = resource_path("fc_token_symbolic.svg")
    if path:
        icon = QIcon(path)
        if not icon.isNull():
            return icon

    return load_app_icon()


def recolor_icon(base_icon: QIcon, color: QColor, size: int = 24) -> QIcon:
    """Recolor a monochrome icon to the given color, preserving alpha."""
    if base_icon.isNull():
        return base_icon

    pm = base_icon.pixmap(size, size)
    if pm.isNull():
        return base_icon

    pm_colored = QPixmap(pm.size())
    pm_colored.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pm_colored)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.drawPixmap(0, 0, pm)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pm_colored.rect(), color)
    painter.end()

    icon = QIcon()
    icon.addPixmap(pm_colored)
    return icon


def create_attention_icon(base_icon: QIcon, size: int = 24) -> QIcon:
    """Create a copy of the tray icon with a small red dot in the top-right corner."""
    if base_icon.isNull():
        return base_icon

    pm = base_icon.pixmap(size, size)
    if pm.isNull():
        return base_icon

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(220, 0, 0))

    radius = size // 6
    margin = size // 8
    center = QPoint(size - margin - radius, margin + radius)

    painter.drawEllipse(center, radius, radius)
    painter.end()

    attention_icon = QIcon()
    attention_icon.addPixmap(pm)
    return attention_icon


def is_dark_theme() -> bool:
    """Heuristic: check the window background color luminance to guess dark theme."""
    app = QApplication.instance()
    if app is None:
        return False

    palette = app.palette()
    color = palette.window().color()
    r, g, b = color.red(), color.green(), color.blue()
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return luminance < 0.5
