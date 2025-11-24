"""Configuration constants for fc-token."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Global application configuration and user-visible constants."""

    # User-facing metadata
    app_name: str = "File Centipede Activation Helper"
    version: str = "0.2.0"

    # URLs
    file_centipede_url: str = "https://filecxx.com/"
    file_centipede_buy_url: str = "https://w.filecxx.com/tpl/login.html"
    default_codes_url: str = "http://filecxx.com/en_US/activation_code.html"

    # Optional project page (UI “About” dialog references it)
    project_url: str = "https://github.com/UglyEgg/fc_token"

    # Default local timezone (used when environment TIMEZONE is not set)
    default_timezone: str = "UTC"

    # Timezone used by the File Centipede activation code page timestamps
    file_centipede_timezone: str = "Asia/Shanghai"

    # Desktop integration / .desktop metadata
    desktop_filename: str = "fc_token.desktop"
    desktop_exec: str = "fc-token"
    desktop_icon_name: str = "fc_token"
    desktop_comment: str = "File Centipede activation helper"
    desktop_categories: str = "Network;Utility;"
    desktop_startup_notify: bool = False

    # QSettings keys / namespaces
    settings_org: str = "fc_token"
    settings_app: str = "settings"

    # Keys for user-configurable behavior
    key_refresh_interval: str = "refresh_interval"
    key_auto_refresh: str = "auto_refresh_enabled"
    key_icon_mode: str = "icon_mode"  # "auto" | "light" | "dark"
    key_timezone: str = "timezone"  # user-selected IANA timezone name


# Instantiate a single shared config (acts like immutable constants)
CONFIG = AppConfig()


# Re-export for compatibility with existing imports
APP_NAME = CONFIG.app_name
APP_VERSION = CONFIG.version

FILE_CENTIPEDE_URL = CONFIG.file_centipede_url
FILE_CENTIPEDE_BUY_URL = CONFIG.file_centipede_buy_url
DEFAULT_CODES_URL = CONFIG.default_codes_url
DEFAULT_TIMEZONE = CONFIG.default_timezone
FILE_CENTIPEDE_TIMEZONE = CONFIG.file_centipede_timezone

# Desktop-related exports
DESKTOP_FILENAME = CONFIG.desktop_filename
DESKTOP_EXEC = CONFIG.desktop_exec
DESKTOP_ICON_NAME = CONFIG.desktop_icon_name
DESKTOP_COMMENT = CONFIG.desktop_comment
DESKTOP_CATEGORIES = CONFIG.desktop_categories
DESKTOP_STARTUP_NOTIFY = CONFIG.desktop_startup_notify

SETTINGS_ORG = CONFIG.settings_org
SETTINGS_APP = CONFIG.settings_app

KEY_REFRESH_INTERVAL = CONFIG.key_refresh_interval
KEY_AUTO_REFRESH = CONFIG.key_auto_refresh
KEY_ICON_MODE = CONFIG.key_icon_mode
KEY_TIMEZONE = CONFIG.key_timezone

__all__ = [
    "CONFIG",
    "APP_NAME",
    "APP_VERSION",
    "FILE_CENTIPEDE_URL",
    "FILE_CENTIPEDE_BUY_URL",
    "DEFAULT_CODES_URL",
    "DEFAULT_TIMEZONE",
    "FILE_CENTIPEDE_TIMEZONE",
    "DESKTOP_FILENAME",
    "DESKTOP_EXEC",
    "DESKTOP_ICON_NAME",
    "DESKTOP_COMMENT",
    "DESKTOP_CATEGORIES",
    "DESKTOP_STARTUP_NOTIFY",
    "SETTINGS_ORG",
    "SETTINGS_APP",
    "KEY_REFRESH_INTERVAL",
    "KEY_AUTO_REFRESH",
    "KEY_ICON_MODE",
    "KEY_TIMEZONE",
]
