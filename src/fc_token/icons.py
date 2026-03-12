"""Icon and theme helpers for fc-token.

This module provides:
- Loading icons from system theme or bundled resources.
- Recoloring monochrome icons.
- Creating “attention” versions of tray icons.
- Detecting dark/light theme heuristically.
"""

from __future__ import annotations

from importlib.resources import files

from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QApplication

# Module-level icon caches to avoid repeated lookups and disk reads.
_APP_ICON: QIcon | None = None
_TRAY_BASE_ICON: QIcon | None = None

# KDE / Plasma symbolic tray icons commonly land around this logical size.
# We render at device-pixel-ratio-aware physical size to avoid blur.
DEFAULT_TRAY_LOGICAL_SIZE = 22


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


def _load_theme_icon(name: str) -> QIcon:
    """Load an icon from the active theme by name."""
    try:
        icon = QIcon.fromTheme(name)
    except Exception:
        return QIcon()
    return icon


def _load_resource_icon(resource_name: str) -> QIcon:
    """Load an icon from packaged resources by name."""
    path = _resource_path(resource_name)
    if not path:
        return QIcon()
    try:
        return QIcon(path)
    except Exception:
        return QIcon()


def _primary_device_pixel_ratio() -> float:
    """Return the most relevant device pixel ratio for icon rasterization."""
    app = QApplication.instance()
    if app is None:
        return 1.0

    screen = app.primaryScreen()
    if screen is None:
        return 1.0

    try:
        dpr = float(screen.devicePixelRatio())
    except Exception:
        return 1.0

    return dpr if dpr > 0 else 1.0


def _render_icon_pixmap(base_icon: QIcon, logical_size: int) -> QPixmap:
    """Render an icon to a DPR-aware pixmap for tray use.

    This reduces blur by rasterizing the icon at physical pixel size rather
    than rendering a too-small pixmap and letting the tray scale it later.
    """
    if base_icon.isNull():
        return QPixmap()

    dpr = _primary_device_pixel_ratio()
    physical_size = max(1, round(logical_size * dpr))
    pm = base_icon.pixmap(QSize(physical_size, physical_size))
    if pm.isNull():
        return pm

    pm.setDevicePixelRatio(dpr)
    return pm


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_app_icon() -> QIcon:
    """Load the application window icon.

    Priority:
        1. Theme icon “fc_token”
        2. Packaged resource “fc_token.png”
        3. Empty icon

    The result is cached for the lifetime of the process to avoid repeated
    theme lookups and disk reads.
    """
    global _APP_ICON
    if _APP_ICON is not None and not _APP_ICON.isNull():
        return _APP_ICON

    icon = _load_theme_icon("fc_token")
    if icon.isNull():
        icon = _load_resource_icon("fc_token.png")

    _APP_ICON = icon
    return icon


def load_tray_base_icon() -> QIcon:
    """Load the base monochrome tray icon used for the tray.

    Priority:
        1. Theme icon “fc_token-symbolic”
        2. Bundled SVG “fc_token-symbolic.svg”
        3. Theme icon “fc_token”
        4. Fallback to application icon

    The result is cached for the lifetime of the process.
    """
    global _TRAY_BASE_ICON
    if _TRAY_BASE_ICON is not None and not _TRAY_BASE_ICON.isNull():
        return _TRAY_BASE_ICON

    # 1) Prefer an installed symbolic icon from the theme.
    icon = _load_theme_icon("fc_token-symbolic")
    if not icon.isNull():
        _TRAY_BASE_ICON = icon
        return icon

    # 2) Then prefer the bundled symbolic SVG over the normal app icon.
    icon = _load_resource_icon("fc_token-symbolic.svg")
    if not icon.isNull():
        _TRAY_BASE_ICON = icon
        return icon

    # 3) Only then fall back to the non-symbolic themed app icon.
    icon = _load_theme_icon("fc_token")
    if not icon.isNull():
        _TRAY_BASE_ICON = icon
        return icon

    # 4) Final fallback.
    fallback = load_app_icon()
    _TRAY_BASE_ICON = fallback
    return fallback


# ---------------------------------------------------------------------------
# Icon manipulation
# ---------------------------------------------------------------------------


def recolor_icon(
    base_icon: QIcon,
    color: QColor,
    size: int = DEFAULT_TRAY_LOGICAL_SIZE,
) -> QIcon:
    """Recolor a monochrome icon to the given color, preserving alpha.

    The source icon is rendered at device-pixel-ratio-aware size first so the
    resulting tray pixmap remains sharper on HiDPI and Plasma trays.
    """
    if base_icon.isNull():
        return base_icon

    pm = _render_icon_pixmap(base_icon, size)
    if pm.isNull():
        return base_icon

    out = QPixmap(pm.size())
    out.setDevicePixelRatio(pm.devicePixelRatio())
    out.fill(Qt.GlobalColor.transparent)

    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    painter.drawPixmap(0, 0, pm)

    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(out.rect(), color)
    painter.end()

    icon = QIcon()
    icon.addPixmap(out)
    return icon


def create_attention_icon(
    base_icon: QIcon,
    size: int = DEFAULT_TRAY_LOGICAL_SIZE,
) -> QIcon:
    """Create an icon with a small red “attention” dot in the corner."""
    if base_icon.isNull():
        return base_icon

    pm = _render_icon_pixmap(base_icon, size)
    if pm.isNull():
        return base_icon

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(220, 0, 0))

    logical_width = pm.width() / pm.devicePixelRatio()
    logical_height = pm.height() / pm.devicePixelRatio()

    radius = int(max(1, logical_width // 6))
    margin = int(max(1, logical_width // 8))
    center = QPoint(
        int(logical_width - margin - radius),
        int(margin + radius),
    )

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

    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return luminance < 0.5
