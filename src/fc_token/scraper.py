"""Scraping and parsing File Centipede activation codes."""

from __future__ import annotations

import re
from datetime import datetime, tzinfo
from typing import Any

import requests

from .config import DEFAULT_CODES_URL
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


def clean_token(raw: str) -> str:
    """Extract the actual activation token from a noisy string.

    The page sometimes includes trailing HTML/JS after the token. This function
    returns the first long run of valid token characters, or a stripped version
    of the input if no such run is found.
    """
    m = TOKEN_RE.search(raw)
    return m.group(0) if m else raw.strip()


def _parse_datetime(value: str, *, tz: tzinfo = UTC) -> datetime:
    """Parse a timestamp string from the page into an aware UTC datetime."""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    # The source timestamps are treated as UTC.
    return dt.replace(tzinfo=tz)


def parse_codes(html: str, *, tz: tzinfo = UTC) -> list[CodeEntry]:
    """Parse activation codes from the HTML page text.

    The page uses blocks of the form:

        2024-01-01 00:00:00 - 2024-02-01 00:00:00
        <one or more lines containing the activation code>

    Codes may span multiple lines; non-empty lines following the date range
    are concatenated until the next date range or end of input.
    """
    lines = html.splitlines()
    codes: list[CodeEntry] = []

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        m = DATE_RE.match(line)
        if not m:
            i += 1
            continue

        start_str, end_str = m.groups()

        # Find the first non-empty line after the date range as the start of the code.
        j = i + 1
        while j < n and not lines[j].strip():
            j += 1
        if j >= n:
            break

        code_line = lines[j].strip()
        k = j + 1

        # Some codes may break across lines; concatenate until the next date range
        # or a blank line immediately preceding one.
        while k < n:
            next_line = lines[k].strip()
            if DATE_RE.match(next_line):
                break
            if next_line:
                code_line += next_line
            k += 1

        code = clean_token(code_line)
        try:
            start = _parse_datetime(start_str, tz=tz)
            end = _parse_datetime(end_str, tz=tz)
        except ValueError:
            # Skip malformed date ranges but continue scanning.
            i = k
            continue

        codes.append(CodeEntry(start=start, end=end, code=code))
        i = k

    # Keep entries ordered for predictable behaviour.
    codes.sort(key=lambda c: c.start)
    return codes


def fetch_codes(url: str = DEFAULT_CODES_URL, *, tz: tzinfo = UTC) -> list[CodeEntry]:
    """Download and parse activation codes from the File Centipede site.

    Raises:
        requests.RequestException: if the HTTP request fails.
    """
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return parse_codes(resp.text, tz=tz)


def get_code_for_date(target: datetime, codes: list[CodeEntry]) -> str | None:
    """Return the activation code valid at the given datetime, if any.

    `target` may be naive (treated as UTC) or timezone-aware (converted to UTC).
    The first matching entry in `codes` is returned; if none match, `None`
    is returned.
    """
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    else:
        target = target.astimezone(UTC)

    # `codes` are typically sorted by `start`, but we don't strictly rely on it.
    for entry in codes:
        if entry.contains(target):
            return entry.code
    return None
