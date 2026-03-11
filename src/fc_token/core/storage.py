"""SQLite-backed persistence for activation codes and refresh metadata."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Sequence

from fc_token.models import CodeEntry, UTC

_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True, slots=True)
class FetchRunRecord:
    """Stored metadata for one refresh attempt."""

    started_utc: datetime
    finished_utc: datetime
    success: bool
    identity_label: str | None = None
    raw_bytes: int | None = None
    code_count: int | None = None
    http_status: int | None = None
    error_kind: str | None = None
    error_message: str | None = None


class SQLiteTokenStore:
    """Persist activation codes and refresh metadata in SQLite."""

    def __init__(
        self,
        db_path: Path,
        *,
        tz: tzinfo = UTC,
        legacy_json_path: Path | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.tz = tz
        self.legacy_json_path = Path(legacy_json_path) if legacy_json_path else None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._import_legacy_json_if_needed()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS tokens (
                    start_utc TEXT NOT NULL,
                    end_utc TEXT NOT NULL,
                    code TEXT NOT NULL,
                    source_timezone TEXT,
                    source_url TEXT,
                    first_seen_utc TEXT,
                    last_seen_utc TEXT,
                    fetch_run_id INTEGER,
                    PRIMARY KEY (start_utc, code),
                    FOREIGN KEY (fetch_run_id) REFERENCES fetch_runs(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS fetch_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_utc TEXT NOT NULL,
                    finished_utc TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    http_status INTEGER,
                    identity_label TEXT,
                    raw_bytes INTEGER,
                    code_count INTEGER,
                    error_kind TEXT,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def _import_legacy_json_if_needed(self) -> None:
        if self.legacy_json_path is None or not self.legacy_json_path.exists():
            return
        if self.load_codes():
            return

        try:
            raw = json.loads(self.legacy_json_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, list):
            return

        codes: list[CodeEntry] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                codes.append(CodeEntry.from_dict(item, tz=self.tz))
            except Exception:
                continue

        if codes:
            self.save_codes(codes)

    @staticmethod
    def _format_dt(value: datetime) -> str:
        normalized = (
            value.astimezone(UTC)
            if value.tzinfo is not None
            else value.replace(tzinfo=UTC)
        )
        return normalized.strftime(_DATETIME_FMT)

    def _parse_dt(self, value: str) -> datetime:
        return datetime.strptime(value, _DATETIME_FMT).replace(tzinfo=self.tz)

    def load_codes(self) -> list[CodeEntry]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT start_utc, end_utc, code FROM tokens ORDER BY start_utc ASC, code ASC"
            ).fetchall()

        codes: list[CodeEntry] = []
        for row in rows:
            codes.append(
                CodeEntry(
                    start=self._parse_dt(row["start_utc"]),
                    end=self._parse_dt(row["end_utc"]),
                    code=str(row["code"]),
                )
            )
        return codes

    def save_codes(self, codes: Sequence[CodeEntry]) -> None:
        ordered = sorted(list(codes), key=lambda entry: (entry.start, entry.code))
        with self._connection() as conn:
            conn.execute("DELETE FROM tokens")
            conn.executemany(
                """
                INSERT INTO tokens (
                    start_utc,
                    end_utc,
                    code,
                    source_timezone,
                    source_url,
                    first_seen_utc,
                    last_seen_utc,
                    fetch_run_id
                ) VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL)
                """,
                [
                    (
                        self._format_dt(entry.start),
                        self._format_dt(entry.end),
                        entry.code,
                    )
                    for entry in ordered
                ],
            )

    def purge(self) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM tokens")
            conn.execute("DELETE FROM fetch_runs")
            conn.execute("DELETE FROM app_state")

    def set_app_state(self, key: str, value: str) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO app_state(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_app_state(self, key: str) -> str | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else str(row["value"])

    def record_fetch_run(self, record: FetchRunRecord) -> int:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO fetch_runs (
                    started_utc,
                    finished_utc,
                    success,
                    http_status,
                    identity_label,
                    raw_bytes,
                    code_count,
                    error_kind,
                    error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._format_dt(record.started_utc),
                    self._format_dt(record.finished_utc),
                    1 if record.success else 0,
                    record.http_status,
                    record.identity_label,
                    record.raw_bytes,
                    record.code_count,
                    record.error_kind,
                    record.error_message,
                ),
            )
            return int(cursor.lastrowid)

    def load_latest_fetch_run(self) -> FetchRunRecord | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT started_utc, finished_utc, success, http_status,
                       identity_label, raw_bytes, code_count, error_kind, error_message
                FROM fetch_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return FetchRunRecord(
            started_utc=self._parse_dt(row["started_utc"]),
            finished_utc=self._parse_dt(row["finished_utc"]),
            success=bool(row["success"]),
            http_status=row["http_status"],
            identity_label=row["identity_label"],
            raw_bytes=row["raw_bytes"],
            code_count=row["code_count"],
            error_kind=row["error_kind"],
            error_message=row["error_message"],
        )
