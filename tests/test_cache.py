"""Tests for fc_token.cache."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

PY311_PLUS = sys.version_info >= (3, 11)

try:
    from PyQt6.QtCore import QStandardPaths

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

if PY311_PLUS and PYQT_AVAILABLE:
    from fc_token.cache import CodeCache
    from fc_token.core.source import SourceFetchResult
    from fc_token.models import CodeEntry, UTC
else:
    CodeCache = None
    CodeEntry = None
    SourceFetchResult = None
    UTC = timezone.utc


@unittest.skipUnless(
    PYQT_AVAILABLE and PY311_PLUS,
    "PyQt6 and Python 3.11+ are required for cache path resolution",
)
class CodeCacheTests(unittest.TestCase):
    """Coverage for cache refresh behavior and persistence."""

    def test_refresh_merges_and_filters_expired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "fc_token.cache.QStandardPaths.writableLocation",
                return_value=str(Path(tmp_dir)),
            ):
                cache = CodeCache()

            expired = CodeEntry(
                start=datetime(2000, 1, 1, 0, 0, 0, tzinfo=UTC),
                end=datetime(2000, 1, 2, 0, 0, 0, tzinfo=UTC),
                code="EXPIRED",
            )
            active = CodeEntry(
                start=datetime(2099, 1, 1, 0, 0, 0, tzinfo=UTC),
                end=datetime(2099, 1, 2, 0, 0, 0, tzinfo=UTC),
                code="ACTIVE",
            )
            fresh = CodeEntry(
                start=datetime(2099, 2, 1, 0, 0, 0, tzinfo=UTC),
                end=datetime(2099, 2, 2, 0, 0, 0, tzinfo=UTC),
                code="FRESH",
            )

            cache.save([expired, active])

            result = SourceFetchResult(
                codes=[fresh],
                identity_label="TestAgent",
                raw_bytes=1234,
                fetched_at_utc=datetime(2099, 1, 1, 12, 0, 0, tzinfo=UTC),
                url="http://example.com",
                raw_text="irrelevant",
            )
            with patch(
                "fc_token.core.source.ActivationSourceClient.fetch_codes",
                return_value=result,
            ):
                refreshed = cache.refresh("http://example.com", use_network=True)

        codes = {entry.code for entry in refreshed}
        self.assertEqual(codes, {"ACTIVE", "FRESH", "EXPIRED"})
        self.assertEqual(cache.last_identity_used, "TestAgent")
        self.assertEqual(cache.last_scrape_raw_bytes, 1234)
        self.assertEqual(cache.last_scraped_codes_count, 1)

    def test_refresh_retains_recent_expired_token_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "fc_token.cache.QStandardPaths.writableLocation",
                return_value=str(Path(tmp_dir)),
            ):
                cache = CodeCache(max_expired_tokens=2)

            oldest_expired = CodeEntry(
                start=datetime(2099, 1, 1, 0, 0, 0, tzinfo=UTC),
                end=datetime(2099, 1, 2, 0, 0, 0, tzinfo=UTC),
                code="OLD-1",
            )
            middle_expired = CodeEntry(
                start=datetime(2099, 1, 3, 0, 0, 0, tzinfo=UTC),
                end=datetime(2099, 1, 4, 0, 0, 0, tzinfo=UTC),
                code="OLD-2",
            )
            newest_expired = CodeEntry(
                start=datetime(2099, 1, 5, 0, 0, 0, tzinfo=UTC),
                end=datetime(2099, 1, 6, 0, 0, 0, tzinfo=UTC),
                code="OLD-3",
            )
            fresh = CodeEntry(
                start=datetime(2099, 2, 1, 0, 0, 0, tzinfo=UTC),
                end=datetime(2099, 2, 2, 0, 0, 0, tzinfo=UTC),
                code="FRESH",
            )

            cache.save([oldest_expired, middle_expired, newest_expired])

            result = SourceFetchResult(
                codes=[fresh],
                identity_label="TestAgent",
                raw_bytes=1234,
                fetched_at_utc=datetime(2099, 2, 1, 12, 0, 0, tzinfo=UTC),
                url="http://example.com",
                raw_text="irrelevant",
            )
            with patch(
                "fc_token.core.source.ActivationSourceClient.fetch_codes",
                return_value=result,
            ):
                refreshed = cache.refresh("http://example.com", use_network=True)

        codes = {entry.code for entry in refreshed}
        self.assertEqual(codes, {"OLD-2", "OLD-3", "FRESH"})


if __name__ == "__main__":
    unittest.main()
