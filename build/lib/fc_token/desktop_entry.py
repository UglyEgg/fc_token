"""Helpers for building .desktop file content from config."""

from __future__ import annotations

from fc_token.config import (
    APP_NAME,
    DESKTOP_COMMENT,
    DESKTOP_EXEC,
    DESKTOP_ICON_NAME,
    DESKTOP_CATEGORIES,
    DESKTOP_STARTUP_NOTIFY,
)


def build_launcher_desktop() -> str:
    """Return the .desktop content for the main launcher.

    This is used by the installer to create the menu entry.
    All values except the format itself come from config.py.
    """
    startup_notify = "true" if DESKTOP_STARTUP_NOTIFY else "false"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Comment={DESKTOP_COMMENT}\n"
        f"Exec={DESKTOP_EXEC}\n"
        f"Icon={DESKTOP_ICON_NAME}\n"
        "Terminal=false\n"
        f"Categories={DESKTOP_CATEGORIES}\n"
        f"StartupNotify={startup_notify}\n"
    )


def build_autostart_desktop() -> str:
    """Return the .desktop content for the autostart entry.

    This reuses the main launcher content and adds the autostart hint.
    We keep the autostart-specific key here so the template and logic
    remain centralized.
    """
    content = build_launcher_desktop()
    if "X-GNOME-Autostart-enabled" not in content:
        content += "X-GNOME-Autostart-enabled=true\n"
    return content
