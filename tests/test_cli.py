"""CLI smoke tests for fc-token."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

PY311_PLUS = sys.version_info >= (3, 11)

try:
    import PyQt6  # noqa: F401

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

if PY311_PLUS:
    from fc_token.config import APP_NAME, APP_VERSION
else:
    APP_NAME = ""
    APP_VERSION = ""


@unittest.skipUnless(
    PYQT_AVAILABLE and PY311_PLUS,
    "PyQt6 and Python 3.11+ are required for CLI entry points",
)
class CliSmokeTests(unittest.TestCase):
    """Ensure CLI entry points respond as expected."""

    def test_version_flag_outputs_version(self) -> None:
        """--version returns 0 and prints the app name and version."""
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(["src", env.get("PYTHONPATH", "")]).strip(
            os.pathsep
        )
        env["QT_QPA_PLATFORM"] = "offscreen"

        result = subprocess.run(
            [sys.executable, "-m", "fc_token.app", "--version"],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn(f"{APP_NAME} {APP_VERSION}", result.stdout.strip())

    def test_self_test_flag_succeeds(self) -> None:
        """--self-test returns 0 in a headless environment."""
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(["src", env.get("PYTHONPATH", "")]).strip(
            os.pathsep
        )
        env["QT_QPA_PLATFORM"] = "offscreen"

        result = subprocess.run(
            [sys.executable, "-m", "fc_token.app", "--self-test"],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
