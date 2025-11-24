"""Configuration constants for fc-token."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Global application configuration and user-visible constants."""

    # User-facing metadata
    app_name: str = "File Centipede Activation Helper"
    version: str = "0.1.5"

    # URLs
    file_centipede_url: str = "https://filecxx.com/"
    file_centipede_buy_url: str = "https://w.filecxx.com/tpl/login.html"
    default_codes_url: str = "http://filecxx.com/en_US/activation_code.html"

    # Optional project page (UI “About” dialog references it)
    project_url: str = "https://github.com/UglyEgg/fc_token"

    # Default local timezone (used when environment TIMEZONE is not set)
    default_timezone: str = "UTC"

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
    "SETTINGS_ORG",
    "SETTINGS_APP",
    "KEY_REFRESH_INTERVAL",
    "KEY_AUTO_REFRESH",
    "KEY_ICON_MODE",
    "KEY_TIMEZONE",
]
