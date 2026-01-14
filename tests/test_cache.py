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
    from fc_token.models import CodeEntry, UTC
else:
    CodeCache = None
    CodeEntry = None
    UTC = timezone.utc


@unittest.skipUnless(
    PYQT_AVAILABLE and PY311_PLUS,
    "PyQt6 and Python 3.11+ are required for cache path resolution",
)
class CodeCacheTests(unittest.TestCase):
    """Coverage for cache refresh behavior and persistence."""

    def test_refresh_merges_and_filters_expired(self) -> None:
        """refresh merges remote data and removes expired entries."""
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

            with patch(
                "fc_token.cache.fetch_codes_with_identity",
                return_value=([fresh], "TestAgent", 1234),
            ):
                refreshed = cache.refresh("http://example.com", use_network=True)

        codes = {entry.code for entry in refreshed}
        self.assertEqual(codes, {"ACTIVE", "FRESH"})
        self.assertEqual(cache.last_identity_used, "TestAgent")
        self.assertEqual(cache.last_scrape_raw_bytes, 1234)
        self.assertEqual(cache.last_scraped_codes_count, 1)


if __name__ == "__main__":
    unittest.main()
