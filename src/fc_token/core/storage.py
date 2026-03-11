"""SQLite-backed persistence for activation codes, diagnostics, and local stats."""

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
_INSTALL_UTC_KEY = "lifecycle/install_utc"
_TOTAL_FOREGROUND_SECONDS_KEY = "lifecycle/total_foreground_seconds"
DEFAULT_MAX_EXPIRED_TOKENS = 150


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
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    """Current persisted refresh diagnostics."""

    last_refresh_utc: str | None
    last_success_refresh_utc: str | None
    last_failure_refresh_utc: str | None
    last_status: str | None
    last_error_kind: str | None
    last_error_message: str | None
    last_identity_used: str | None
    last_scrape_raw_bytes: int | None
    last_scraped_codes_count: int
    recent_fetch_runs: tuple[FetchRunRecord, ...]


@dataclass(frozen=True, slots=True)
class StatisticsSnapshot:
    """Aggregate local statistics built from persisted refresh runs."""

    total_runs: int
    success_count: int
    failure_count: int
    total_bytes: int
    total_codes: int
    median_duration_ms: int | None
    average_duration_ms: int | None
    last_duration_ms: int | None
    fastest_duration_ms: int | None
    slowest_duration_ms: int | None
    identity_counts: tuple[tuple[str, int], ...]
    install_utc: str | None
    total_foreground_seconds: int
    recent_fetch_runs: tuple[FetchRunRecord, ...]


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
                    error_message TEXT,
                    duration_ms INTEGER
                );

                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "fetch_runs", "duration_ms", "INTEGER")

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_sql: str,
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        if any(str(row["name"]) == column_name for row in rows):
            return
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
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

    @staticmethod
    def _parse_optional_int(value: str | None) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

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
            self._set_app_state_on_connection(conn, key, value)

    def _set_app_state_on_connection(
        self, conn: sqlite3.Connection, key: str, value: str
    ) -> None:
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

    def ensure_installation_timestamp(self, value: datetime) -> str:
        current = self.get_app_state(_INSTALL_UTC_KEY)
        if current:
            return current
        text = value.astimezone(UTC).isoformat()
        self.set_app_state(_INSTALL_UTC_KEY, text)
        return text

    def add_foreground_seconds(self, seconds: int) -> None:
        seconds = max(0, int(seconds))
        current = self._parse_optional_int(self.get_app_state(_TOTAL_FOREGROUND_SECONDS_KEY)) or 0
        self.set_app_state(_TOTAL_FOREGROUND_SECONDS_KEY, str(current + seconds))

    def record_fetch_run(self, record: FetchRunRecord) -> int:
        with self._connection() as conn:
            return self._record_fetch_run_on_connection(conn, record)

    def _record_fetch_run_on_connection(
        self, conn: sqlite3.Connection, record: FetchRunRecord
    ) -> int:
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
                error_message,
                duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                record.duration_ms,
            ),
        )
        return int(cursor.lastrowid)

    def record_refresh_outcome(
        self,
        record: FetchRunRecord,
        *,
        max_fetch_runs: int = 100,
    ) -> int:
        with self._connection() as conn:
            run_id = self._record_fetch_run_on_connection(conn, record)
            finished_text = self._format_dt(record.finished_utc)

            self._set_app_state_on_connection(conn, "last_refresh_utc", finished_text)
            self._set_app_state_on_connection(
                conn,
                "last_status",
                "success" if record.success else "failure",
            )

            if record.identity_label is not None:
                self._set_app_state_on_connection(
                    conn, "last_identity_used", record.identity_label
                )
            if record.raw_bytes is not None:
                self._set_app_state_on_connection(
                    conn, "last_scrape_raw_bytes", str(record.raw_bytes)
                )
            if record.code_count is not None:
                self._set_app_state_on_connection(
                    conn, "last_scraped_codes_count", str(record.code_count)
                )

            if record.success:
                self._set_app_state_on_connection(
                    conn, "last_success_refresh_utc", finished_text
                )
                self._set_app_state_on_connection(conn, "last_error_kind", "")
                self._set_app_state_on_connection(conn, "last_error_message", "")
            else:
                self._set_app_state_on_connection(
                    conn, "last_failure_refresh_utc", finished_text
                )
                self._set_app_state_on_connection(
                    conn, "last_error_kind", record.error_kind or ""
                )
                self._set_app_state_on_connection(
                    conn, "last_error_message", record.error_message or ""
                )

            self._enforce_retention_on_connection(conn, max_fetch_runs=max_fetch_runs)
            return run_id

    def load_latest_fetch_run(self) -> FetchRunRecord | None:
        runs = self.load_recent_fetch_runs(limit=1)
        return runs[0] if runs else None

    def load_recent_fetch_runs(self, *, limit: int = 10) -> list[FetchRunRecord]:
        limit = max(1, int(limit))
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT started_utc, finished_utc, success, http_status,
                       identity_label, raw_bytes, code_count, error_kind, error_message,
                       duration_ms
                FROM fetch_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        runs: list[FetchRunRecord] = []
        for row in rows:
            runs.append(
                FetchRunRecord(
                    started_utc=self._parse_dt(row["started_utc"]),
                    finished_utc=self._parse_dt(row["finished_utc"]),
                    success=bool(row["success"]),
                    http_status=row["http_status"],
                    identity_label=row["identity_label"],
                    raw_bytes=row["raw_bytes"],
                    code_count=row["code_count"],
                    error_kind=row["error_kind"],
                    error_message=row["error_message"],
                    duration_ms=row["duration_ms"],
                )
            )
        return runs

    def enforce_retention(self, *, max_fetch_runs: int = 100) -> None:
        with self._connection() as conn:
            self._enforce_retention_on_connection(conn, max_fetch_runs=max_fetch_runs)

    def _enforce_retention_on_connection(
        self, conn: sqlite3.Connection, *, max_fetch_runs: int
    ) -> None:
        max_fetch_runs = max(1, int(max_fetch_runs))
        conn.execute(
            """
            DELETE FROM fetch_runs
            WHERE id NOT IN (
                SELECT id
                FROM fetch_runs
                ORDER BY id DESC
                LIMIT ?
            )
            """,
            (max_fetch_runs,),
        )

    def load_diagnostics(self, *, limit: int = 10) -> DiagnosticsSnapshot:
        keys = (
            "last_refresh_utc",
            "last_success_refresh_utc",
            "last_failure_refresh_utc",
            "last_status",
            "last_error_kind",
            "last_error_message",
            "last_identity_used",
            "last_scrape_raw_bytes",
            "last_scraped_codes_count",
        )
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM app_state WHERE key IN ({})".format(
                    ",".join("?" for _ in keys)
                ),
                keys,
            ).fetchall()

        values = {str(row["key"]): str(row["value"]) for row in rows}
        return DiagnosticsSnapshot(
            last_refresh_utc=values.get("last_refresh_utc") or None,
            last_success_refresh_utc=values.get("last_success_refresh_utc") or None,
            last_failure_refresh_utc=values.get("last_failure_refresh_utc") or None,
            last_status=values.get("last_status") or None,
            last_error_kind=values.get("last_error_kind") or None,
            last_error_message=values.get("last_error_message") or None,
            last_identity_used=values.get("last_identity_used") or None,
            last_scrape_raw_bytes=self._parse_optional_int(
                values.get("last_scrape_raw_bytes")
            ),
            last_scraped_codes_count=(
                self._parse_optional_int(values.get("last_scraped_codes_count")) or 0
            ),
            recent_fetch_runs=tuple(self.load_recent_fetch_runs(limit=limit)),
        )

    def load_statistics(self, *, limit: int = 200) -> StatisticsSnapshot:
        runs = self.load_recent_fetch_runs(limit=max(1, int(limit)))
        total_runs = len(runs)
        success_count = sum(1 for run in runs if run.success)
        failure_count = total_runs - success_count
        total_bytes = sum(int(run.raw_bytes or 0) for run in runs if run.success)
        total_codes = sum(int(run.code_count or 0) for run in runs if run.success)

        durations = [
            int(run.duration_ms)
            for run in runs
            if run.duration_ms is not None and int(run.duration_ms) >= 0
        ]
        if durations:
            ordered = sorted(durations)
            middle = len(ordered) // 2
            if len(ordered) % 2 == 1:
                median_duration_ms = ordered[middle]
            else:
                median_duration_ms = int((ordered[middle - 1] + ordered[middle]) / 2)
            average_duration_ms = int(sum(ordered) / len(ordered))
            fastest_duration_ms = ordered[0]
            slowest_duration_ms = ordered[-1]
            last_duration_ms = durations[0]
        else:
            median_duration_ms = None
            average_duration_ms = None
            fastest_duration_ms = None
            slowest_duration_ms = None
            last_duration_ms = None

        identity_counts_map: dict[str, int] = {}
        for run in runs:
            if not run.identity_label:
                continue
            identity_counts_map[run.identity_label] = (
                identity_counts_map.get(run.identity_label, 0) + 1
            )
        identity_counts = tuple(
            sorted(identity_counts_map.items(), key=lambda item: (-item[1], item[0]))
        )

        install_utc = self.get_app_state(_INSTALL_UTC_KEY)
        total_foreground_seconds = (
            self._parse_optional_int(self.get_app_state(_TOTAL_FOREGROUND_SECONDS_KEY))
            or 0
        )

        return StatisticsSnapshot(
            total_runs=total_runs,
            success_count=success_count,
            failure_count=failure_count,
            total_bytes=total_bytes,
            total_codes=total_codes,
            median_duration_ms=median_duration_ms,
            average_duration_ms=average_duration_ms,
            last_duration_ms=last_duration_ms,
            fastest_duration_ms=fastest_duration_ms,
            slowest_duration_ms=slowest_duration_ms,
            identity_counts=identity_counts,
            install_utc=install_utc,
            total_foreground_seconds=total_foreground_seconds,
            recent_fetch_runs=tuple(runs),
        )
