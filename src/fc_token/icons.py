"""Icon and theme helpers for fc-token.

This module provides:
- Loading icons from system theme or bundled resources.
- Recoloring monochrome icons.
- Creating “attention” versions of tray icons.
- Detecting dark/light theme heuristically.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Sequence

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Resource loading
# ---------------------------------------------------------------------------


def _resource_path(name: str) -> str | None:
    """Return an absolute path to a packaged resource, if present.

    Bundled resources should live under:
        fc_token/resources/<name>
    """
    try:
        pkg_root = files("fc_token.resources")
        path = pkg_root.joinpath(name)
        if path.is_file():
            return str(path)
    except Exception:
        pass
    return None


def _load_icon_with_fallbacks(
    *,
    theme_names: Sequence[str],
    resource_name: str | None = None,
) -> QIcon:
    """Try loading an icon with multiple strategies:

    1. Try each name in `theme_names` via QIcon.fromTheme().
    2. If `resource_name` is provided, try packaged resources.
    3. Fallback: return an empty QIcon().
    """
    # Try theme icons first
    for name in theme_names:
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon

    # Try resource
    if resource_name is not None:
        path = _resource_path(resource_name)
        if path:
            icon = QIcon(path)
            if not icon.isNull():
                return icon

    return QIcon()  # final fallback


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_app_icon() -> QIcon:
    """Load the application window icon.

    Priority:
        1. Theme icon “fc_token”
        2. Packaged resource “fc_token.png”
        3. Empty icon
    """
    return _load_icon_with_fallbacks(
        theme_names=["fc_token"],
        resource_name="fc_token.png",
    )


def load_tray_base_icon() -> QIcon:
    """Load the base tray icon (monochrome duck).

    Priority:
        1. Theme icon “fc_token-symbolic”
        2. Theme icon “fc_token”
        3. Bundled SVG “fc_token_symbolic.svg”
        4. Fallback to application icon
    """
    icon = _load_icon_with_fallbacks(
        theme_names=[
            "fc_token-symbolic",
            "fc_token",
        ],
        resource_name="fc_token_symbolic.svg",
    )
    if not icon.isNull():
        return icon
    return load_app_icon()


# ---------------------------------------------------------------------------
# Icon manipulation
# ---------------------------------------------------------------------------


def recolor_icon(base_icon: QIcon, color: QColor, size: int = 24) -> QIcon:
    """Recolor a monochrome icon to the given color, preserving alpha."""
    if base_icon.isNull():
        return base_icon

    pm = base_icon.pixmap(size, size)
    if pm.isNull():
        return base_icon

    # Create a transparent pixmap
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)

    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw the base icon
    painter.drawPixmap(0, 0, pm)

    # Apply color using SourceIn composition
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(out.rect(), color)
    painter.end()

    icon = QIcon()
    icon.addPixmap(out)
    return icon


def create_attention_icon(base_icon: QIcon, size: int = 24) -> QIcon:
    """Create an icon with a small red “attention” dot in the corner."""
    if base_icon.isNull():
        return base_icon

    pm = base_icon.pixmap(size, size)
    if pm.isNull():
        return base_icon

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(220, 0, 0))

    # Position a small dot
    radius = size // 6
    margin = size // 8
    center = QPoint(size - margin - radius, margin + radius)

    painter.drawEllipse(center, radius, radius)
    painter.end()

    icon = QIcon()
    icon.addPixmap(pm)
    return icon


# ---------------------------------------------------------------------------
# Theme detection
# ---------------------------------------------------------------------------


def is_dark_theme() -> bool:
    """Heuristic: detect whether the system palette looks dark.

    Checks the luminance of the window background color.
    """
    app = QApplication.instance()
    if app is None:
        return False

    color = app.palette().window().color()
    r, g, b = color.red(), color.green(), color.blue()

    # Perceptual luminance
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return luminance < 0.5
