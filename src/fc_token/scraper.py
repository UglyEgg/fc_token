"""Scraping and parsing File Centipede activation codes."""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

import requests

from .config import DEFAULT_CODES_URL
from .models import CodeEntry

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{40,}")
DATE_RE = re.compile(
    r"\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*-\s*"
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)


def clean_token(raw: str) -> str:
    """Strip HTML/JS tail from a line that should contain the code.

    File Centipede activation codes appear to use a URL-safe Base64-like alphabet:
    A-Z, a-z, 0-9, '-' and '_'. Sometimes the scraper accidentally captures trailing
    HTML or JavaScript after the real code. This function extracts the first long
    run of valid token characters and returns it.
    """
    m = TOKEN_RE.search(raw)
    return m.group(0) if m else raw.strip()


def parse_codes(html: str) -> List[CodeEntry]:
    """Parse activation codes from the HTML page text."""
    lines = html.splitlines()
    codes: List[CodeEntry] = []

    for i, line in enumerate(lines):
        m = DATE_RE.match(line)
        if not m:
            continue

        start_str, end_str = m.groups()

        # Find the first non-empty line after the date range as code start
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            continue

        code_line = lines[j].strip()
        k = j + 1

        # Some codes may break across lines; concatenate until the next date range
        while k < len(lines):
            next_line = lines[k].strip()
            if DATE_RE.match(next_line):
                break
            if next_line:
                code_line += next_line
            k += 1

        code = clean_token(code_line)
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        codes.append(CodeEntry(start=start, end=end, code=code))

    return codes


def fetch_codes(url: str = DEFAULT_CODES_URL) -> List[CodeEntry]:
    """Download and parse activation codes from the File Centipede site."""
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return parse_codes(resp.text)


def get_code_for_date(target: datetime, codes: List[CodeEntry]) -> Optional[str]:
    """Return the activation code valid at the given UTC datetime.

    If no code matches, returns None.
    """
    for entry in codes:
        if entry.start <= target <= entry.end:
            return entry.code
    return None
