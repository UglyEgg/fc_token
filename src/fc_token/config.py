"""Configuration constants for fc-token."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Global application configuration and user-visible constants."""

    # User-facing metadata
    app_name: str = "File Centipede Activation Helper"
    version: str = "0.3.0"

    # URLs
    file_centipede_url: str = "https://filecxx.com/"
    file_centipede_buy_url: str = "https://w.filecxx.com/tpl/login.html"
    default_codes_url: str = "http://filecxx.com/en_US/activation_code.html"

    # Optional project page (UI "About" dialog references it)
    project_url: str = "https://github.com/UglyEgg/fc_token"

    # Default local timezone (used when environment TIMEZONE is not set)
    default_timezone: str = "UTC"
    # Timezone used by the File Centipede site (source timestamps)
    source_timezone: str = "Asia/Shanghai"

    # Desktop integration / .desktop metadata
    desktop_filename: str = "fc_token.desktop"
    desktop_exec: str = "fc-token"
    desktop_icon_name: str = "fc_token"
    desktop_comment: str = "File Centipede activation helper"
    desktop_categories: str = "Network;Utility;"
    desktop_startup_notify: bool = False

    # QSettings organisation & application names
    settings_org: str = "UglyEgg"
    settings_app: str = "fc_token"

    # Settings keys
    key_refresh_interval: str = "refresh_interval"
    key_auto_refresh: str = "auto_refresh_enabled"
    key_icon_mode: str = "icon_mode"
    key_timezone: str = "timezone"

    # Browser identities (label, user-agent) used for scraping
    browser_identities: List[Tuple[str, str]] = (
        (
            "Chrome (Linux)",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ),
        (
            "Chrome (Windows)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ),
        (
            "Firefox (Linux)",
            "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) " "Gecko/20100101 Firefox/125.0",
        ),
        (
            "Firefox (Windows)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
            "Gecko/20100101 Firefox/125.0",
        ),
        (
            "Edge (Windows)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
            "Edg/124.0.0.0",
        ),
    )


_CONFIG = AppConfig()

APP_NAME = _CONFIG.app_name
APP_VERSION = _CONFIG.version

FILE_CENTIPEDE_URL = _CONFIG.file_centipede_url
FILE_CENTIPEDE_BUY_URL = _CONFIG.file_centipede_buy_url
PROJECT_URL = _CONFIG.project_url

DEFAULT_CODES_URL = _CONFIG.default_codes_url
DEFAULT_TIMEZONE = _CONFIG.default_timezone
FILE_CENTIPEDE_TIMEZONE = _CONFIG.source_timezone

DESKTOP_FILENAME = _CONFIG.desktop_filename
DESKTOP_EXEC = _CONFIG.desktop_exec
DESKTOP_ICON_NAME = _CONFIG.desktop_icon_name
DESKTOP_COMMENT = _CONFIG.desktop_comment
DESKTOP_CATEGORIES = _CONFIG.desktop_categories
DESKTOP_STARTUP_NOTIFY = _CONFIG.desktop_startup_notify

SETTINGS_ORG = _CONFIG.settings_org
SETTINGS_APP = _CONFIG.settings_app

KEY_REFRESH_INTERVAL = _CONFIG.key_refresh_interval
KEY_AUTO_REFRESH = _CONFIG.key_auto_refresh
KEY_ICON_MODE = _CONFIG.key_icon_mode
KEY_TIMEZONE = _CONFIG.key_timezone

BROWSER_IDENTITIES = list(_CONFIG.browser_identities)

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "FILE_CENTIPEDE_URL",
    "FILE_CENTIPEDE_BUY_URL",
    "PROJECT_URL",
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
    "BROWSER_IDENTITIES",
]
