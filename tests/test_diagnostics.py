from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from fc_token.core.storage import DiagnosticsSnapshot, FetchRunRecord
from fc_token.diagnostics import format_diagnostics_snapshot, format_diagnostics_snapshot_html
from fc_token.models import UTC


class DiagnosticsFormattingTests(unittest.TestCase):
    def test_formats_success_snapshot(self) -> None:
        snapshot = DiagnosticsSnapshot(
            last_refresh_utc="2099-01-01 12:00:00",
            last_success_refresh_utc="2099-01-01 12:00:00",
            last_failure_refresh_utc=None,
            last_status="success",
            last_error_kind=None,
            last_error_message=None,
            last_identity_used="Agent-A",
            last_scrape_raw_bytes=1234,
            last_scraped_codes_count=2,
            recent_fetch_runs=(
                FetchRunRecord(
                    started_utc=datetime(2099, 1, 1, 12, 0, 0, tzinfo=UTC),
                    finished_utc=datetime(2099, 1, 1, 12, 0, 0, tzinfo=UTC),
                    success=True,
                    identity_label="Agent-A",
                    raw_bytes=1234,
                    code_count=2,
                ),
            ),
        )

        text = format_diagnostics_snapshot(
            snapshot,
            local_tz=ZoneInfo("UTC"),
            local_tz_name="UTC",
        )

        self.assertIn("Status: success", text)
        self.assertIn("Identity: Agent-A", text)
        self.assertIn("Bytes received: 1234", text)
        self.assertIn("Codes parsed: 2", text)
        self.assertIn("Recent refresh runs:", text)
        self.assertIn("success", text)

    def test_formats_failure_snapshot_with_error(self) -> None:
        snapshot = DiagnosticsSnapshot(
            last_refresh_utc="2099-01-01 12:00:00",
            last_success_refresh_utc=None,
            last_failure_refresh_utc="2099-01-01 12:00:00",
            last_status="failure",
            last_error_kind="SourceParseError",
            last_error_message="No valid codes parsed from source response.",
            last_identity_used=None,
            last_scrape_raw_bytes=None,
            last_scraped_codes_count=0,
            recent_fetch_runs=(
                FetchRunRecord(
                    started_utc=datetime(2099, 1, 1, 12, 0, 0, tzinfo=UTC),
                    finished_utc=datetime(2099, 1, 1, 12, 0, 0, tzinfo=UTC),
                    success=False,
                    identity_label=None,
                    raw_bytes=None,
                    code_count=0,
                    error_kind="SourceParseError",
                    error_message="No valid codes parsed from source response.",
                ),
            ),
        )

        text = format_diagnostics_snapshot(
            snapshot,
            local_tz=ZoneInfo("America/Chicago"),
            local_tz_name="America/Chicago",
        )

        self.assertIn("Status: failure", text)
        self.assertIn(
            "Last error: SourceParseError: No valid codes parsed from source response.",
            text,
        )
        self.assertIn(
            "error: SourceParseError: No valid codes parsed from source response.", text
        )
        self.assertIn("America/Chicago", text)

    def test_formats_empty_run_history(self) -> None:
        snapshot = DiagnosticsSnapshot(
            last_refresh_utc=None,
            last_success_refresh_utc=None,
            last_failure_refresh_utc=None,
            last_status=None,
            last_error_kind=None,
            last_error_message=None,
            last_identity_used=None,
            last_scrape_raw_bytes=None,
            last_scraped_codes_count=0,
            recent_fetch_runs=(),
        )

        text = format_diagnostics_snapshot(
            snapshot,
            local_tz=ZoneInfo("UTC"),
            local_tz_name="UTC",
        )

        self.assertIn("Status: unknown", text)
        self.assertIn("Recent refresh runs:", text)
        self.assertIn("- none recorded", text)

    def test_formats_html_snapshot_with_sections(self) -> None:
        snapshot = DiagnosticsSnapshot(
            last_refresh_utc="2099-01-01 12:00:00",
            last_success_refresh_utc="2099-01-01 12:00:00",
            last_failure_refresh_utc="2099-01-01 13:00:00",
            last_status="failure",
            last_error_kind="SourceNetworkError",
            last_error_message="request timed out",
            last_identity_used="Agent-Z",
            last_scrape_raw_bytes=77,
            last_scraped_codes_count=0,
            recent_fetch_runs=(
                FetchRunRecord(
                    started_utc=datetime(2099, 1, 1, 12, 0, 0, tzinfo=UTC),
                    finished_utc=datetime(2099, 1, 1, 12, 0, 5, tzinfo=UTC),
                    success=False,
                    identity_label="Agent-Z",
                    raw_bytes=77,
                    code_count=0,
                    error_kind="SourceNetworkError",
                    error_message="request timed out",
                ),
            ),
        )

        text = format_diagnostics_snapshot_html(
            snapshot,
            local_tz=ZoneInfo("UTC"),
            local_tz_name="UTC",
        )

        self.assertIn("🩺 Refresh health", text)
        self.assertIn("🌐 Last network activity", text)
        self.assertIn("❗ Last error", text)
        self.assertIn("SourceNetworkError", text)
        self.assertIn("Agent-Z", text)


if __name__ == "__main__":
    unittest.main()
