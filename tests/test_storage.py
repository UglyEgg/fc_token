from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fc_token.core.storage import (
    DiagnosticsSnapshot,
    FetchRunRecord,
    SQLiteTokenStore,
    StatisticsSnapshot,
)
from fc_token.models import CodeEntry, UTC


class SQLiteTokenStoreTests(unittest.TestCase):
    def test_save_and_load_codes_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SQLiteTokenStore(Path(tmp_dir) / "codes.sqlite3")
            codes = [
                CodeEntry(
                    start=datetime(2099, 1, 1, 0, 0, 0, tzinfo=UTC),
                    end=datetime(2099, 1, 2, 0, 0, 0, tzinfo=UTC),
                    code="ACTIVE",
                ),
                CodeEntry(
                    start=datetime(2099, 2, 1, 0, 0, 0, tzinfo=UTC),
                    end=datetime(2099, 2, 2, 0, 0, 0, tzinfo=UTC),
                    code="FRESH",
                ),
            ]
            store.save_codes(codes)
            loaded = store.load_codes()

        self.assertEqual(
            [(c.start_str, c.code) for c in loaded],
            [(c.start_str, c.code) for c in codes],
        )

    def test_imports_legacy_json_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            legacy_path = tmp_path / "file_centipede_codes.json"
            payload = [
                {
                    "start_date": "2099-01-01 00:00:00",
                    "end_date": "2099-01-02 00:00:00",
                    "code": "LEGACY",
                }
            ]
            legacy_path.write_text(json.dumps(payload), encoding="utf-8")
            store = SQLiteTokenStore(
                tmp_path / "codes.sqlite3",
                legacy_json_path=legacy_path,
            )
            loaded = store.load_codes()

        self.assertEqual([entry.code for entry in loaded], ["LEGACY"])

    def test_records_fetch_runs_and_app_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SQLiteTokenStore(Path(tmp_dir) / "codes.sqlite3")
            when = datetime(2099, 1, 1, 12, 0, 0, tzinfo=UTC)
            run_id = store.record_refresh_outcome(
                FetchRunRecord(
                    started_utc=when,
                    finished_utc=when,
                    success=True,
                    identity_label="TestAgent",
                    raw_bytes=1234,
                    code_count=2,
                )
            )
            latest = store.load_latest_fetch_run()
            diagnostics = store.load_diagnostics(limit=5)

        self.assertGreater(run_id, 0)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertTrue(latest.success)
        self.assertEqual(latest.identity_label, "TestAgent")
        self.assertEqual(latest.raw_bytes, 1234)
        self.assertEqual(latest.code_count, 2)
        self.assertEqual(diagnostics.last_status, "success")
        self.assertEqual(diagnostics.last_identity_used, "TestAgent")
        self.assertEqual(diagnostics.last_scrape_raw_bytes, 1234)
        self.assertEqual(diagnostics.last_scraped_codes_count, 2)

    def test_retention_keeps_newest_fetch_runs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SQLiteTokenStore(Path(tmp_dir) / "codes.sqlite3")
            for day in range(1, 5):
                when = datetime(2099, 1, day, 12, 0, 0, tzinfo=UTC)
                store.record_refresh_outcome(
                    FetchRunRecord(
                        started_utc=when,
                        finished_utc=when,
                        success=(day % 2 == 0),
                        identity_label=f"Agent-{day}",
                        raw_bytes=1000 + day,
                        code_count=day,
                    ),
                    max_fetch_runs=2,
                )

            runs = store.load_recent_fetch_runs(limit=10)

        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].identity_label, "Agent-4")
        self.assertEqual(runs[1].identity_label, "Agent-3")

    def test_failure_diagnostics_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SQLiteTokenStore(Path(tmp_dir) / "codes.sqlite3")
            when = datetime(2099, 1, 1, 12, 0, 0, tzinfo=UTC)
            store.record_refresh_outcome(
                FetchRunRecord(
                    started_utc=when,
                    finished_utc=when,
                    success=False,
                    error_kind="SourceParseError",
                    error_message="No valid codes parsed from source response.",
                ),
                max_fetch_runs=5,
            )
            diagnostics = store.load_diagnostics(limit=5)

        self.assertIsInstance(diagnostics, DiagnosticsSnapshot)
        self.assertEqual(diagnostics.last_status, "failure")
        self.assertEqual(diagnostics.last_error_kind, "SourceParseError")
        self.assertEqual(
            diagnostics.last_error_message,
            "No valid codes parsed from source response.",
        )
        self.assertEqual(len(diagnostics.recent_fetch_runs), 1)
        self.assertFalse(diagnostics.recent_fetch_runs[0].success)



    def test_statistics_are_derived_from_database_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SQLiteTokenStore(Path(tmp_dir) / "codes.sqlite3")
            store.ensure_installation_timestamp(datetime(2099, 1, 1, 0, 0, 0, tzinfo=UTC))
            store.add_foreground_seconds(120)
            first = datetime(2099, 1, 1, 12, 0, 0, tzinfo=UTC)
            second = datetime(2099, 1, 2, 12, 0, 0, tzinfo=UTC)
            store.record_refresh_outcome(
                FetchRunRecord(
                    started_utc=first,
                    finished_utc=first,
                    success=True,
                    identity_label="Agent-A",
                    raw_bytes=1200,
                    code_count=2,
                    duration_ms=1500,
                ),
                max_fetch_runs=10,
            )
            store.record_refresh_outcome(
                FetchRunRecord(
                    started_utc=second,
                    finished_utc=second,
                    success=False,
                    error_kind="SourceNetworkError",
                    error_message="timeout",
                    duration_ms=2500,
                ),
                max_fetch_runs=10,
            )
            snapshot = store.load_statistics(limit=10)

        self.assertIsInstance(snapshot, StatisticsSnapshot)
        self.assertEqual(snapshot.total_runs, 2)
        self.assertEqual(snapshot.success_count, 1)
        self.assertEqual(snapshot.failure_count, 1)
        self.assertEqual(snapshot.total_bytes, 1200)
        self.assertEqual(snapshot.total_codes, 2)
        self.assertEqual(snapshot.average_duration_ms, 2000)
        self.assertEqual(snapshot.total_foreground_seconds, 120)
        self.assertEqual(snapshot.identity_counts, (("Agent-A", 1),))

if __name__ == "__main__":
    unittest.main()
