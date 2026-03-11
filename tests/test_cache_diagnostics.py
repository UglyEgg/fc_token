from __future__ import annotations

import sys
import tempfile
import unittest
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
else:
    CodeCache = None


@unittest.skipUnless(
    PYQT_AVAILABLE and PY311_PLUS,
    "PyQt6 and Python 3.11+ are required for cache path resolution",
)
class CodeCacheDiagnosticsTests(unittest.TestCase):
    def test_refresh_failure_is_recorded_in_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "fc_token.cache.QStandardPaths.writableLocation",
                return_value=str(Path(tmp_dir)),
            ):
                cache = CodeCache(max_fetch_runs=5)

            with patch(
                "fc_token.core.source.ActivationSourceClient.fetch_codes",
                side_effect=RuntimeError("network down"),
            ):
                with self.assertRaises(RuntimeError):
                    cache.refresh("http://example.com", use_network=True)

            diagnostics = cache.get_diagnostics(limit=5)

        self.assertEqual(diagnostics.last_status, "failure")
        self.assertEqual(diagnostics.last_error_kind, "RuntimeError")
        self.assertEqual(diagnostics.last_error_message, "network down")
        self.assertEqual(len(diagnostics.recent_fetch_runs), 1)
        self.assertFalse(diagnostics.recent_fetch_runs[0].success)


if __name__ == "__main__":
    unittest.main()
