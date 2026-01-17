"""Scraping and parsing File Centipede activation codes.

Refactored to:
- Keep the original parsing logic and UTC semantics.
- Use a small pool of realistic browser User-Agent strings for requests.
- Optionally reuse a module-level `requests.Session` for connection reuse.
"""

from __future__ import annotations

import random
import re
from datetime import datetime, tzinfo
from typing import Any, List
from zoneinfo import ZoneInfo

import requests

from .config import DEFAULT_CODES_URL, BROWSER_IDENTITIES, FILE_CENTIPEDE_TIMEZONE
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

# Small pool of realistic desktop browser User-Agent strings.
USER_AGENTS: List[str] = [
    # Chrome, Linux
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    # Chrome, Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    # Firefox, Linux
    (
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
    # Firefox, Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
    # Edge, Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
    ),
]


_SOURCE_TIMEZONE: tzinfo | None = None
_SOURCE_TIMEZONE_NAME: str | None = None
_LAST_PARSED_TZ_KEY: str | None = None


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


def _get_random_user_agent() -> str:
    """Return a random realistic browser User-Agent string."""
    return random.choice(USER_AGENTS)


# Optional module-level session for connection reuse.
_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
)


def _get_session() -> requests.Session:
    """Return the shared requests session used for scraping."""
    return _SESSION


def clean_token(raw: str) -> str:
    """Extract the actual activation token from a noisy string.

    The page sometimes includes trailing HTML/JS after the token. This function
    returns the first long run of valid token characters, or a stripped version
    of the input if no such run is found.
    """
    m = TOKEN_RE.search(raw)
    return m.group(0) if m else raw.strip()


def _parse_datetime(value: str, *, tz: tzinfo) -> datetime:
    """Parse a timestamp string from the page into an aware datetime.

    The source timestamps are assumed to be in the provided timezone.
    """
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=tz)


def _parse_codes_with_timezone(html: str, tz: tzinfo) -> list[CodeEntry]:
    """Parse activation codes from HTML using the specified source timezone."""
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
            start = _parse_datetime(start_str, tz=tz).astimezone(UTC)
            end = _parse_datetime(end_str, tz=tz).astimezone(UTC)
        except ValueError:
            # Skip malformed date ranges but continue scanning.
            i = k
            continue

        codes.append(CodeEntry(start=start, end=end, code=code))
        i = k

    # Keep entries ordered by start time for predictable behaviour.
    codes.sort(key=lambda c: c.start)
    return codes


def _score_codes(codes: list[CodeEntry], now_utc: datetime) -> tuple[int, float]:
    """Return a score tuple for selecting the best timezone parse."""
    if not codes:
        return (2, float("inf"), 0)

    nearest = float("inf")
    active = False
    future_count = 0
    for entry in codes:
        if entry.start <= now_utc <= entry.end:
            active = True
            nearest = 0.0
            break
        if entry.end >= now_utc:
            future_count += 1
        if now_utc < entry.start:
            delta = (entry.start - now_utc).total_seconds()
        else:
            delta = (now_utc - entry.end).total_seconds()
        if delta < nearest:
            nearest = delta

    return (0 if active else 1, nearest, -future_count)


def _unique_timezones(candidates: list[tzinfo]) -> list[tzinfo]:
    """Return timezones, removing duplicates by key/repr."""
    unique: list[tzinfo] = []
    seen: set[str] = set()
    for tz in candidates:
        key = getattr(tz, "key", None) or str(tz)
        if key in seen:
            continue
        seen.add(key)
        unique.append(tz)
    return unique


def _tz_key(value: tzinfo) -> str:
    """Return a stable identifier for the timezone."""
    return getattr(value, "key", None) or str(value)


def parse_codes(html: str, *, tz: tzinfo | None = None) -> list[CodeEntry]:
    """Parse activation codes from the HTML page text.

    The page uses blocks of the form:

        2024-01-01 00:00:00 - 2024-02-01 00:00:00
        <one or more lines containing the activation code>

    Codes may span multiple lines; non-empty lines following the date range
    are concatenated until the next date range or end of input. Parsed
    timestamps are converted to UTC for internal storage.
    """
    if tz is not None:
        return _parse_codes_with_timezone(html, tz)

    global _LAST_PARSED_TZ_KEY
    local_tz = datetime.now().astimezone().tzinfo
    candidates = _unique_timezones(
        [
            tzinfo_item
            for tzinfo_item in (_get_source_timezone(), UTC, local_tz)
            if tzinfo_item
        ]
    )
    if _LAST_PARSED_TZ_KEY is not None:
        for tzinfo_item in candidates:
            if _tz_key(tzinfo_item) == _LAST_PARSED_TZ_KEY:
                candidates = [tzinfo_item] + [
                    candidate
                    for candidate in candidates
                    if _tz_key(candidate) != _LAST_PARSED_TZ_KEY
                ]
                break

    now_utc = datetime.now(UTC)
    best_codes: list[CodeEntry] = []
    best_score = (2, float("inf"), 0)
    best_candidate: tzinfo | None = None
    for candidate in candidates:
        parsed = _parse_codes_with_timezone(html, candidate)
        score = _score_codes(parsed, now_utc)
        if score < best_score:
            best_score = score
            best_codes = parsed
            best_candidate = candidate

    if best_candidate is not None:
        _LAST_PARSED_TZ_KEY = _tz_key(best_candidate)

    return best_codes


def fetch_codes(
    url: str = DEFAULT_CODES_URL, *, tz: tzinfo | None = None
) -> list[CodeEntry]:
    """Download and parse activation codes from the File Centipede site.

    Raises:
        requests.RequestException: if the HTTP request fails.
    """
    headers = {"User-Agent": _get_random_user_agent()}
    resp = _get_session().get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return parse_codes(resp.text, tz=tz)


def _choose_identity() -> tuple[str, str]:
    """Return (identity_label, user_agent) chosen from configured identities.

    Uses the BROWSER_IDENTITIES list from fc_token.config so that
    browser strings can be updated centrally without touching the
    scraper logic.
    """
    return random.choice(BROWSER_IDENTITIES)


def fetch_codes_with_identity(
    url: str = DEFAULT_CODES_URL, *, tz: tzinfo | None = None
) -> tuple[list[CodeEntry], str, int]:
    """Download and parse codes, returning (codes, identity_label, bytes_scraped).

    bytes_scraped is the size of the HTTP response body in bytes.
    """
    identity_label, user_agent = _choose_identity()
    headers = {"User-Agent": user_agent}
    resp = _get_session().get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    body_bytes = len(resp.content or b"")
    codes = parse_codes(resp.text, tz=tz)
    return codes, identity_label, body_bytes


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
