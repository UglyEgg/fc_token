"""Tests for fc_token.scraper."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

PY311_PLUS = sys.version_info >= (3, 11)

if PY311_PLUS:
    from fc_token.core.source import SourceFetchResult
    from fc_token.models import UTC, CodeEntry
    from fc_token.scraper import (
        clean_token,
        fetch_codes_with_identity,
        get_code_for_date,
        parse_codes,
    )
else:
    UTC = timezone.utc
    CodeEntry = None
    SourceFetchResult = None
    clean_token = None
    fetch_codes_with_identity = None
    get_code_for_date = None
    parse_codes = None


@unittest.skipUnless(PY311_PLUS, "fc-token requires Python 3.11+ for typing.Self")
class ScraperTests(unittest.TestCase):
    """Coverage for the parsing and selection helpers."""

    def test_parse_codes_handles_multiline_tokens(self) -> None:
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

    def test_parse_codes_defaults_to_source_timezone(self) -> None:
        html = "2024-01-01 00:00:00 - 2024-01-01 01:00:00\nTOKEN123\n"
        codes = parse_codes(html)
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0].start, datetime(2023, 12, 31, 16, 0, 0, tzinfo=UTC))
        self.assertEqual(codes[0].end, datetime(2023, 12, 31, 17, 0, 0, tzinfo=UTC))

    def test_clean_token_prefers_long_match(self) -> None:
        token = "A" * 40
        raw = f"{token} trailing"
        self.assertEqual(clean_token(raw), token)

    def test_get_code_for_date_returns_matching_code(self) -> None:
        html = "2024-01-01 00:00:00 - 2024-01-02 00:00:00\nTOKEN123\n"
        codes = parse_codes(html, tz=UTC)
        target = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        self.assertEqual(get_code_for_date(target, codes), "TOKEN123")

    def test_fetch_codes_with_identity_reports_bytes(self) -> None:
        html = "2024-01-01 00:00:00 - 2024-01-02 00:00:00\nTOKEN123\n"
        expected_codes = [
            CodeEntry(
                start=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end=datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC),
                code="TOKEN123",
            )
        ]
        result = SourceFetchResult(
            codes=expected_codes,
            identity_label="Test",
            raw_bytes=len(html.encode("utf-8")),
            fetched_at_utc=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            url="http://example.com",
            raw_text=html,
        )

        with patch("fc_token.core.source.ActivationSourceClient.fetch_codes", return_value=result):
            codes, identity, raw_bytes = fetch_codes_with_identity("http://example.com")

        self.assertEqual(identity, "Test")
        self.assertEqual(raw_bytes, len(html.encode("utf-8")))
        self.assertEqual(codes[0].code, "TOKEN123")


if __name__ == "__main__":
    unittest.main()
