"""Tests for fc_token.scraper."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

PY311_PLUS = sys.version_info >= (3, 11)

if PY311_PLUS:
    from fc_token.models import UTC
    from fc_token.scraper import (
        clean_token,
        fetch_codes_with_identity,
        get_code_for_date,
        parse_codes,
    )
else:
    UTC = timezone.utc
    clean_token = None
    fetch_codes_with_identity = None
    get_code_for_date = None
    parse_codes = None


class FakeResponse:
    """Simple fake response for testing network helpers."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.content = text.encode("utf-8")

    def raise_for_status(self) -> None:
        return None


@unittest.skipUnless(PY311_PLUS, "fc-token requires Python 3.11+ for typing.Self")
class ScraperTests(unittest.TestCase):
    """Coverage for the parsing and selection helpers."""

    def test_parse_codes_handles_multiline_tokens(self) -> None:
        """parse_codes concatenates multiline tokens and sorts entries."""
        html = (
            "2024-01-01 00:00:00 - 2024-01-02 00:00:00\n"
            "ABC\n"
            "DEF\n"
            "\n"
            "2024-01-03 00:00:00 - 2024-01-04 00:00:00\n"
            "GHIJK\n"
        )
        codes = parse_codes(html, tz=UTC)

        self.assertEqual(len(codes), 2)
        self.assertEqual(codes[0].code, "ABCDEF")
        self.assertEqual(codes[1].code, "GHIJK")

    def test_clean_token_prefers_long_match(self) -> None:
        """clean_token extracts the first long token run when present."""
        token = "A" * 40
        raw = f"{token} trailing"
        self.assertEqual(clean_token(raw), token)

    def test_get_code_for_date_returns_matching_code(self) -> None:
        """get_code_for_date returns the code containing the target moment."""
        html = "2024-01-01 00:00:00 - 2024-01-02 00:00:00\nTOKEN123\n"
        codes = parse_codes(html, tz=UTC)
        target = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        self.assertEqual(get_code_for_date(target, codes), "TOKEN123")

    def test_fetch_codes_with_identity_reports_bytes(self) -> None:
        """fetch_codes_with_identity returns codes, identity, and byte count."""
        html = "2024-01-01 00:00:00 - 2024-01-02 00:00:00\nTOKEN123\n"
        fake_response = FakeResponse(html)

        with patch("fc_token.scraper._choose_identity", return_value=("Test", "UA")):
            with patch("fc_token.scraper._SESSION.get", return_value=fake_response):
                codes, identity, raw_bytes = fetch_codes_with_identity("http://example.com")

        self.assertEqual(identity, "Test")
        self.assertEqual(raw_bytes, len(html.encode("utf-8")))
        self.assertEqual(codes[0].code, "TOKEN123")


if __name__ == "__main__":
    unittest.main()
