"""Parsing helpers for File Centipede activation codes.

This module intentionally focuses on parsing and code selection. Network access
lives in ``fc_token.core.source`` so the refresh engine can be reused by other
front ends without dragging Qt or tray logic into the core.
"""

from __future__ import annotations

import re
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

from .config import DEFAULT_CODES_URL, FILE_CENTIPEDE_TIMEZONE
from .models import CodeEntry, UTC

# Activation codes appear to use a URL-safe Base64-like alphabet:
# A–Z, a–z, 0–9, '-' and '_', typically at least 40 characters long.
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{40,}")

# Lines that define a validity window look like:
#   2024-01-01 00:00:00 - 2024-02-01 00:00:00
DATE_RE = re.compile(
    r"\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*-\s*"
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)

_SOURCE_TIMEZONE: tzinfo | None = None
_SOURCE_TIMEZONE_NAME: str | None = None


def _get_source_timezone() -> tzinfo:
    """Return the timezone used by the File Centipede site.

    Falls back to UTC if the configured timezone is unavailable.
    """
    global _SOURCE_TIMEZONE
    global _SOURCE_TIMEZONE_NAME
    if _SOURCE_TIMEZONE is not None and _SOURCE_TIMEZONE_NAME == FILE_CENTIPEDE_TIMEZONE:
        return _SOURCE_TIMEZONE
    try:
        _SOURCE_TIMEZONE = ZoneInfo(FILE_CENTIPEDE_TIMEZONE)
    except Exception:
        _SOURCE_TIMEZONE = UTC
    _SOURCE_TIMEZONE_NAME = FILE_CENTIPEDE_TIMEZONE
    return _SOURCE_TIMEZONE


def refresh_source_timezone() -> tzinfo:
    """Force the File Centipede source timezone to be reloaded."""
    global _SOURCE_TIMEZONE
    global _SOURCE_TIMEZONE_NAME
    _SOURCE_TIMEZONE = None
    _SOURCE_TIMEZONE_NAME = None
    return _get_source_timezone()


def clean_token(raw: str) -> str:
    """Extract the actual activation token from a noisy string."""
    match = TOKEN_RE.search(raw)
    return match.group(0) if match else raw.strip()


def _parse_datetime(value: str, *, tz: tzinfo) -> datetime:
    """Parse a source timestamp string into an aware datetime."""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=tz)


def _parse_codes_with_timezone(html: str, tz: tzinfo) -> list[CodeEntry]:
    """Parse activation codes from page text using the specified source timezone."""
    lines = html.splitlines()
    codes: list[CodeEntry] = []

    index = 0
    total_lines = len(lines)
    while index < total_lines:
        line = lines[index]
        match = DATE_RE.match(line)
        if not match:
            index += 1
            continue

        start_str, end_str = match.groups()

        code_index = index + 1
        while code_index < total_lines and not lines[code_index].strip():
            code_index += 1
        if code_index >= total_lines:
            break

        code_line = lines[code_index].strip()
        next_index = code_index + 1
        while next_index < total_lines:
            next_line = lines[next_index].strip()
            if DATE_RE.match(next_line):
                break
            if next_line:
                code_line += next_line
            next_index += 1

        code = clean_token(code_line)
        try:
            start = _parse_datetime(start_str, tz=tz).astimezone(UTC)
            end = _parse_datetime(end_str, tz=tz).astimezone(UTC)
        except ValueError:
            index = next_index
            continue

        codes.append(CodeEntry(start=start, end=end, code=code))
        index = next_index

    codes.sort(key=lambda entry: entry.start)
    return codes


def parse_codes(html: str, *, tz: tzinfo | None = None) -> list[CodeEntry]:
    """Parse activation codes from the HTML page text.

    When ``tz`` is omitted, the configured File Centipede source timezone is
    treated as authoritative.
    """
    effective_tz = tz if tz is not None else _get_source_timezone()
    return _parse_codes_with_timezone(html, effective_tz)


def fetch_codes(
    url: str = DEFAULT_CODES_URL, *, tz: tzinfo | None = None
) -> list[CodeEntry]:
    """Backward-compatible helper that fetches codes via the core source client."""
    from .core.source import ActivationSourceClient

    result = ActivationSourceClient().fetch_codes(url)
    if tz is None:
        return result.codes
    return parse_codes(result.raw_text, tz=tz)


def fetch_codes_with_identity(
    url: str = DEFAULT_CODES_URL, *, tz: tzinfo | None = None
) -> tuple[list[CodeEntry], str, int]:
    """Backward-compatible helper returning (codes, identity_label, bytes_scraped)."""
    from .core.source import ActivationSourceClient

    result = ActivationSourceClient().fetch_codes(url)
    codes = result.codes if tz is None else parse_codes(result.raw_text, tz=tz)
    return codes, result.identity_label, result.raw_bytes


def get_code_for_date(target: datetime, codes: list[CodeEntry]) -> str | None:
    """Return the activation code valid at the given datetime, if any."""
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    else:
        target = target.astimezone(UTC)

    for entry in codes:
        if entry.contains(target):
            return entry.code
    return None
