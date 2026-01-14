"""Tests for fc_token.models."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone

PY311_PLUS = sys.version_info >= (3, 11)

if PY311_PLUS:
    from fc_token.models import CodeEntry, UTC
else:
    CodeEntry = None
    UTC = timezone.utc


@unittest.skipUnless(PY311_PLUS, "fc-token requires Python 3.11+ for typing.Self")
class CodeEntryTests(unittest.TestCase):
    """Coverage for the CodeEntry model helpers."""

    def test_round_trip_dict(self) -> None:
        """CodeEntry converts to and from dicts consistently."""
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC)
        entry = CodeEntry(start=start, end=end, code="ABC123")

        data = entry.to_dict()
        restored = CodeEntry.from_dict(data, tz=UTC)

        self.assertEqual(restored.start, entry.start)
        self.assertEqual(restored.end, entry.end)
        self.assertEqual(restored.code, entry.code)

    def test_contains_accepts_naive_and_aware_datetimes(self) -> None:
        """contains treats naive datetimes as UTC and respects aware values."""
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC)
        entry = CodeEntry(start=start, end=end, code="ABC123")

        naive_inside = datetime(2024, 1, 1, 0, 30, 0)
        aware_inside = datetime(2024, 1, 1, 8, 30, 0, tzinfo=timezone(timedelta(hours=8)))
        outside = datetime(2024, 1, 1, 2, 0, 0, tzinfo=UTC)

        self.assertTrue(entry.contains(naive_inside))
        self.assertTrue(entry.contains(aware_inside))
        self.assertFalse(entry.contains(outside))


if __name__ == "__main__":
    unittest.main()
