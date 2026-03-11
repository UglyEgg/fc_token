from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fc_token.core.storage import FetchRunRecord, SQLiteTokenStore
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
            store.set_app_state("last_identity_used", "TestAgent")
            run_id = store.record_fetch_run(
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
            stored_identity = store.get_app_state("last_identity_used")

        self.assertGreater(run_id, 0)
        self.assertEqual(stored_identity, "TestAgent")
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertTrue(latest.success)
        self.assertEqual(latest.identity_label, "TestAgent")
        self.assertEqual(latest.raw_bytes, 1234)
        self.assertEqual(latest.code_count, 2)


if __name__ == "__main__":
    unittest.main()
