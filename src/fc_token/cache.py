"""On-disk cache management for activation codes.

The cache is now primarily a storage abstraction. Refresh orchestration lives in
``fc_token.core.refresh`` and network access lives in ``fc_token.core.source``.
A legacy ``refresh()`` method is retained for backwards compatibility while the
UI moves to the new core service layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from pathlib import Path
from typing import List, Sequence

from PyQt6.QtCore import QStandardPaths

from .core.storage import FetchRunRecord, SQLiteTokenStore
from .models import CodeEntry, UTC


@dataclass(slots=True)
class CodeCache:
    """Manage persisted activation codes with expiration filtering."""

    app_name: str = "fc_token"
    tz: tzinfo = UTC
    cache_dir: Path | None = field(init=False, default=None)
    cache_path: Path | None = field(init=False, default=None)
    legacy_cache_path: Path | None = field(init=False, default=None)
    _codes: List[CodeEntry] = field(init=False, default_factory=list)
    _loaded: bool = field(init=False, default=False)
    _store: SQLiteTokenStore = field(init=False)
    last_identity_used: str | None = field(init=False, default=None)
    last_scrape_raw_bytes: int | None = field(init=False, default=None)
    last_scraped_codes_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        cache_root = self._get_cache_root()
        base_path = Path(cache_root) if cache_root else Path.home() / ".cache"
        self.cache_dir = base_path / self.app_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.cache_dir / "file_centipede_codes.sqlite3"
        self.legacy_cache_path = self.cache_dir / "file_centipede_codes.json"
        self._store = SQLiteTokenStore(
            self.cache_path,
            tz=self.tz,
            legacy_json_path=self.legacy_cache_path,
        )
        self._hydrate_metadata_from_store()

    def _get_cache_root(self) -> str:
        return QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )

    def _hydrate_metadata_from_store(self) -> None:
        self.last_identity_used = self._store.get_app_state("last_identity_used")
        raw_bytes = self._store.get_app_state("last_scrape_raw_bytes")
        codes_count = self._store.get_app_state("last_scraped_codes_count")
        try:
            self.last_scrape_raw_bytes = None if raw_bytes is None else int(raw_bytes)
        except (TypeError, ValueError):
            self.last_scrape_raw_bytes = None
        try:
            self.last_scraped_codes_count = (
                0 if codes_count is None else int(codes_count)
            )
        except (TypeError, ValueError):
            self.last_scraped_codes_count = 0

    def _load_from_disk(self) -> list[CodeEntry]:
        return self._store.load_codes()

    def _save_to_disk(self, codes: list[CodeEntry]) -> None:
        self._store.save_codes(codes)

    def _persist_refresh_metadata(
        self, *, fetched_at_utc: datetime, success: bool = True
    ) -> None:
        self._store.set_app_state("last_identity_used", self.last_identity_used or "")
        self._store.set_app_state(
            "last_scrape_raw_bytes",
            ""
            if self.last_scrape_raw_bytes is None
            else str(self.last_scrape_raw_bytes),
        )
        self._store.set_app_state(
            "last_scraped_codes_count", str(self.last_scraped_codes_count)
        )
        self._store.set_app_state(
            "last_refresh_utc",
            fetched_at_utc.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._store.record_fetch_run(
            FetchRunRecord(
                started_utc=fetched_at_utc,
                finished_utc=fetched_at_utc,
                success=success,
                identity_label=self.last_identity_used,
                raw_bytes=self.last_scrape_raw_bytes,
                code_count=self.last_scraped_codes_count,
            )
        )

    def get_codes(self) -> list[CodeEntry]:
        if not self._loaded:
            self._codes = self._load_from_disk()
            self._loaded = True
        return list(self._codes)

    def get_active_codes(self, *, now: datetime | None = None) -> list[CodeEntry]:
        now = now or self._now()
        return [entry for entry in self.get_codes() if entry.end >= now]

    def load(self) -> list[CodeEntry]:
        return self.get_codes()

    def save(self, codes: list[CodeEntry]) -> None:
        ordered = sorted(list(codes), key=lambda entry: entry.start)
        self._codes = ordered
        self._loaded = True
        self._save_to_disk(self._codes)

    def merge_and_save(
        self,
        fresh_codes: Sequence[CodeEntry],
        *,
        now: datetime | None = None,
    ) -> list[CodeEntry]:
        now = now or self._now()
        merged: dict[str, CodeEntry] = {
            entry.start_str: entry for entry in self.get_codes()
        }
        for entry in fresh_codes:
            merged[entry.start_str] = entry
        active = [entry for entry in merged.values() if entry.end >= now]
        active.sort(key=lambda entry: entry.start)
        self.save(active)
        self._persist_refresh_metadata(fetched_at_utc=now, success=True)
        return active

    def purge(self) -> None:
        self._codes = []
        self._loaded = True
        self._store.purge()

    def refresh(self, url: str, *, use_network: bool = True) -> list[CodeEntry]:
        """Legacy compatibility wrapper.

        New callers should use :class:`fc_token.core.refresh.RefreshService`.
        """
        if not use_network:
            active = self.get_active_codes(now=self._now())
            self.save(active)
            return active

        from .core.source import ActivationSourceClient

        result = ActivationSourceClient().fetch_codes(url)
        self.last_identity_used = result.identity_label
        self.last_scrape_raw_bytes = result.raw_bytes
        self.last_scraped_codes_count = len(result.codes)
        return self.merge_and_save(result.codes, now=result.fetched_at_utc)

    def _now(self) -> datetime:
        return datetime.now(self.tz)
