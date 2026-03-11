from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

PY311_PLUS = sys.version_info >= (3, 11)
try:
    from PyQt6.QtCore import QStandardPaths  # noqa: F401
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

if PY311_PLUS and PYQT_AVAILABLE:
    from fc_token.cache import CodeCache
    from fc_token.core.refresh import (
        RefreshPolicy,
        RefreshService,
        RefreshStateKind,
        RefreshTrigger,
    )
    from fc_token.core.source import SourceNetworkError
    from fc_token.models import CodeEntry, UTC
else:
    CodeCache = None
    RefreshPolicy = None
    RefreshService = None
    RefreshStateKind = None
    RefreshTrigger = None
    SourceNetworkError = None
    CodeEntry = None
    from datetime import timezone
    UTC = timezone.utc


@unittest.skipUnless(PYQT_AVAILABLE and PY311_PLUS, "PyQt6 and Python 3.11+ required")
class RefreshCoreTests(unittest.TestCase):
    def test_decide_network_use_blocks_when_active_codes_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("fc_token.cache.QStandardPaths.writableLocation", return_value=str(Path(tmp_dir))):
                cache = CodeCache()
            active = CodeEntry(
                start=datetime(2099,1,1,tzinfo=UTC),
                end=datetime(2099,1,2,tzinfo=UTC),
                code='ACTIVE',
            )
            cache.save([active])
            service = RefreshService(cache, policy=RefreshPolicy())
            decision = service.decide_network_use(last_refresh_utc=None)
        self.assertFalse(decision.should_use_network)

    def test_refresh_returns_network_failed_state_on_source_error(self) -> None:
        class FailingClient:
            def fetch_codes(self, url: str):
                raise SourceNetworkError('nope')

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("fc_token.cache.QStandardPaths.writableLocation", return_value=str(Path(tmp_dir))):
                cache = CodeCache()
            service = RefreshService(cache, source_client=FailingClient())
            outcome = service.refresh('http://example.com', trigger=RefreshTrigger.MANUAL, last_refresh_utc=None)
        self.assertEqual(outcome.state.kind, RefreshStateKind.NETWORK_FAILED)


if __name__ == "__main__":
    unittest.main()
