"""Configuration constants for fc-token."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_name: str = "File Centipede Activation Helper"
    version: str = "0.2.0"
    file_centipede_url: str = "https://filecxx.com/"
    file_centipede_buy_url: str = "https://w.filecxx.com/tpl/login.html"
    default_codes_url: str = "http://filecxx.com/en_US/activation_code.html"
    project_url: str = "https://github.com/UglyEgg/fc_token"
    default_timezone: str = "UTC"
    source_timezone: str = "Asia/Shanghai"
    desktop_filename: str = "fc_token.desktop"
    desktop_exec: str = "fc-token"
    desktop_icon_name: str = "fc_token"
    desktop_comment: str = "File Centipede activation helper"
    desktop_categories: str = "Network;Utility;"
    desktop_startup_notify: bool = False
    settings_org: str = "fc_token"
    settings_app: str = "settings"
    key_refresh_interval: str = "refresh_interval"
    key_auto_refresh: str = "auto_refresh_enabled"
    key_icon_mode: str = "icon_mode"
    key_timezone: str = "timezone"
    browser_identities: List[Tuple[str, str]] = None


CONFIG = AppConfig(
    browser_identities=[
        (
            "Chrome (Linux)",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ),
        (
            "Chrome (Windows)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ),
        (
            "Firefox (Linux)",
            "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
        ),
        (
            "Firefox (Windows)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        ),
        (
            "Edge (Windows)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        ),
    ]
)

APP_NAME = CONFIG.app_name
APP_VERSION = CONFIG.version
FILE_CENTIPEDE_URL = CONFIG.file_centipede_url
FILE_CENTIPEDE_BUY_URL = CONFIG.file_centipede_buy_url
PROJECT_URL = CONFIG.project_url
DEFAULT_CODES_URL = CONFIG.default_codes_url
DEFAULT_TIMEZONE = CONFIG.default_timezone
FILE_CENTIPEDE_TIMEZONE = CONFIG.source_timezone
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
BROWSER_IDENTITIES = CONFIG.browser_identities
