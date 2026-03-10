"""Timezone resolution helpers.

This module keeps timezone lookup logic out of the Qt widget helpers so it can
be tested without a GUI runtime. It resolves one canonical timezone choice and
then exposes small convenience wrappers for display and conversion callers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

from fc_token.config import KEY_TIMEZONE, SETTINGS_APP, SETTINGS_ORG

_ZONEINFO_ROOT = Path("/usr/share/zoneinfo")
_LOCALTIME_PATH = Path("/etc/localtime")
_TIMEZONE_FILE_PATH = Path("/etc/timezone")
_FALLBACK_TZ_NAME = "UTC"


class TimezoneSource(str, Enum):
    """Origin of the resolved local timezone."""

    SETTINGS = "settings"
    ENVIRONMENT = "env"
    SYSTEM = "system"
    SYSTEM_FALLBACK = "system-fallback"
    DEFAULT = "default"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class ResolvedTimezone:
    """Canonical result of local timezone resolution."""

    tzinfo: tzinfo
    display_name: str
    canonical_name: str | None
    source: TimezoneSource


def _load_zone(name: str | None) -> ZoneInfo | None:
    """Return a ZoneInfo for a valid IANA timezone name."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        return None


def _read_saved_zone_name() -> str | None:
    """Return the user-selected timezone stored in QSettings, if any."""
    try:
        from PyQt6.QtCore import QSettings
    except Exception:
        return None

    try:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        value = settings.value(KEY_TIMEZONE, "", type=str)
    except Exception:
        return None
    return value or None


def _read_env_zone_name() -> str | None:
    """Return an environment-provided IANA timezone override, if any.

    This intentionally supports only IANA zone names that can be loaded by
    ZoneInfo. Full POSIX TZ expression parsing is out of scope here.
    """
    return os.environ.get("TZ") or os.environ.get("TIMEZONE") or None


def _read_system_zone_name_from_localtime() -> str | None:
    """Infer the system timezone name from /etc/localtime when possible."""
    try:
        resolved = _LOCALTIME_PATH.resolve(strict=True)
    except Exception:
        return None

    try:
        relative = resolved.relative_to(_ZONEINFO_ROOT)
    except Exception:
        return None

    zone_name = relative.as_posix()
    return zone_name or None


def _read_system_zone_name_from_file() -> str | None:
    """Read the timezone name from /etc/timezone when available."""
    try:
        value = _TIMEZONE_FILE_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return value or None


def _read_system_zone_name() -> str | None:
    """Return the operating system's canonical timezone name, if available."""
    for candidate in (
        _read_system_zone_name_from_localtime(),
        _read_system_zone_name_from_file(),
    ):
        if _load_zone(candidate) is not None:
            return candidate
    return None


def _read_system_zone_fallback() -> tzinfo | None:
    """Return a best-effort local tzinfo when no canonical zone name is known."""
    try:
        return datetime.now().astimezone().tzinfo
    except Exception:
        return None


def _display_name_for_zone(value: tzinfo, canonical_name: str | None) -> str:
    """Return a user-facing timezone label."""
    if canonical_name:
        return canonical_name

    try:
        name = datetime.now(value).tzname()
    except Exception:
        name = None
    if isinstance(name, str) and name:
        return name

    text = str(value)
    return text if text else _FALLBACK_TZ_NAME


def resolve_local_timezone(default_tz_name: str) -> ResolvedTimezone:
    """Resolve the effective local timezone used by the application.

    Precedence:
        1. User-selected timezone stored in QSettings.
        2. Environment override (TZ, then TIMEZONE).
        3. Canonical operating system timezone.
        4. Best-effort system local tzinfo if only a fixed offset is available.
        5. Provided default timezone name.
        6. UTC.
    """
    candidates = (
        (TimezoneSource.SETTINGS, _read_saved_zone_name()),
        (TimezoneSource.ENVIRONMENT, _read_env_zone_name()),
        (TimezoneSource.SYSTEM, _read_system_zone_name()),
    )

    for source, zone_name in candidates:
        zone = _load_zone(zone_name)
        if zone is not None and zone_name is not None:
            return ResolvedTimezone(
                tzinfo=zone,
                display_name=zone_name,
                canonical_name=zone_name,
                source=source,
            )

    system_zone = _read_system_zone_fallback()
    if system_zone is not None:
        return ResolvedTimezone(
            tzinfo=system_zone,
            display_name=_display_name_for_zone(system_zone, None),
            canonical_name=None,
            source=TimezoneSource.SYSTEM_FALLBACK,
        )

    default_zone = _load_zone(default_tz_name)
    if default_zone is not None:
        return ResolvedTimezone(
            tzinfo=default_zone,
            display_name=default_tz_name,
            canonical_name=default_tz_name,
            source=TimezoneSource.DEFAULT,
        )

    return ResolvedTimezone(
        tzinfo=timezone.utc,
        display_name=_FALLBACK_TZ_NAME,
        canonical_name=_FALLBACK_TZ_NAME,
        source=TimezoneSource.FALLBACK,
    )


def get_local_zone(default_tz_name: str) -> tzinfo:
    """Return the resolved tzinfo used for local-time display and conversion."""
    return resolve_local_timezone(default_tz_name).tzinfo


def get_local_zone_name(default_tz_name: str) -> str:
    """Return the user-facing label for the resolved local timezone."""
    return resolve_local_timezone(default_tz_name).display_name


def get_local_zone_key(default_tz_name: str) -> str:
    """Return an IANA timezone key suitable for settings and combo preselection."""
    resolved = resolve_local_timezone(default_tz_name)
    if resolved.canonical_name:
        return resolved.canonical_name

    default_zone = _load_zone(default_tz_name)
    if default_zone is not None:
        return default_tz_name

    return _FALLBACK_TZ_NAME


__all__ = [
    "ResolvedTimezone",
    "TimezoneSource",
    "get_local_zone",
    "get_local_zone_key",
    "get_local_zone_name",
    "resolve_local_timezone",
]
