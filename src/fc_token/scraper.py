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

import requests

from .config import DEFAULT_CODES_URL, BROWSER_IDENTITIES
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


def clean_token(raw: str) -> str:
    """Extract the actual activation token from a noisy string.

    The page sometimes includes trailing HTML/JS after the token. This function
    returns the first long run of valid token characters, or a stripped version
    of the input if no such run is found.
    """
    m = TOKEN_RE.search(raw)
    return m.group(0) if m else raw.strip()


def _parse_datetime(value: str, *, tz: tzinfo = UTC) -> datetime:
    """Parse a timestamp string from the page into an aware UTC datetime.

    The source timestamps are treated as UTC.
    """
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
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
    headers = {"User-Agent": _get_random_user_agent()}
    resp = _SESSION.get(url, headers=headers, timeout=15)
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
    url: str = DEFAULT_CODES_URL, *, tz: tzinfo = UTC
) -> tuple[list[CodeEntry], str, int]:
    """Download and parse codes, returning (codes, identity_label, bytes_scraped).

    bytes_scraped is the size of the HTTP response body in bytes.
    """
    identity_label, user_agent = _choose_identity()
    headers = {"User-Agent": user_agent}
    resp = _SESSION.get(url, headers=headers, timeout=15)
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