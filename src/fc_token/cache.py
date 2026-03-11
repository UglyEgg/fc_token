"""On-disk cache management for activation codes.

The cache is now primarily a storage abstraction. Refresh orchestration lives in
``fc_token.core.refresh`` and network access lives in ``fc_token.core.source``.
A legacy ``refresh()`` method is retained for backwards compatibility while the
UI moves to the new core service layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from pathlib import Path
from typing import List, Sequence

from PyQt6.QtCore import QStandardPaths

from .models import CodeEntry, UTC


@dataclass(slots=True)
class CodeCache:
    """Manage on-disk cache of activation codes with expiration filtering."""

    app_name: str = "fc_token"
    tz: tzinfo = UTC
    cache_dir: Path | None = field(init=False, default=None)
    cache_path: Path | None = field(init=False, default=None)
    _codes: List[CodeEntry] = field(init=False, default_factory=list)
    _loaded: bool = field(init=False, default=False)
    last_identity_used: str | None = field(init=False, default=None)
    last_scrape_raw_bytes: int | None = field(init=False, default=None)
    last_scraped_codes_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        cache_root = self._get_cache_root()
        base_path = Path(cache_root) if cache_root else Path.home() / ".cache"
        self.cache_dir = base_path / self.app_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.cache_dir / "file_centipede_codes.json"

    def _get_cache_root(self) -> str:
        return QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )

    def _load_from_disk(self) -> list[CodeEntry]:
        if self.cache_path is None or not self.cache_path.exists():
            return []

        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        codes: list[CodeEntry] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                codes.append(CodeEntry.from_dict(item, tz=self.tz))
            except Exception:
                continue
        return codes

    def _save_to_disk(self, codes: list[CodeEntry]) -> None:
        if self.cache_path is None:
            return
        data = [entry.to_dict() for entry in codes]
        try:
            self.cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

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
        merged: dict[str, CodeEntry] = {entry.start_str: entry for entry in self.get_codes()}
        for entry in fresh_codes:
            merged[entry.start_str] = entry
        active = [entry for entry in merged.values() if entry.end >= now]
        active.sort(key=lambda entry: entry.start)
        self.save(active)
        return active

    def purge(self) -> None:
        self._codes = []
        self._loaded = True
        try:
            if self.cache_path is not None and self.cache_path.exists():
                self.cache_path.unlink()
        except Exception:
            pass

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
