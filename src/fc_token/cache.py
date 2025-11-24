"""On-disk cache management for activation codes.

Refactored to:
- Maintain a small in-memory cache to avoid repeated JSON loads.
- Centralise expiration filtering in `refresh()`.
- Provide a simple, read-only view via `get_codes()`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from pathlib import Path
from typing import List

from PyQt6.QtCore import QStandardPaths

from .models import CodeEntry, UTC
from .scraper import fetch_codes


@dataclass(slots=True)
class CodeCache:
    """Manage on-disk cache of activation codes with expiration filtering.

    All timestamps are stored and compared in UTC.

    This implementation keeps a small in-memory copy of the cache to avoid
    repeated JSON parsing during normal operation.
    """

    app_name: str = "fc_token"
    tz: tzinfo = UTC
    cache_dir: Path | None = field(init=False, default=None)
    cache_path: Path | None = field(init=False, default=None)
    _codes: List[CodeEntry] = field(init=False, default_factory=list)
    _loaded: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        cache_root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        if cache_root:
            base_path = Path(cache_root)
        else:
            # Fallback for environments where QStandardPaths returns an empty string.
            base_path = Path.home() / ".cache"

        self.cache_dir = base_path / self.app_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_path = self.cache_dir / "file_centipede_codes.json"

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _load_from_disk(self) -> list[CodeEntry]:
        """Low-level loader that reads and parses the JSON cache file.

        Malformed entries are ignored.
        """
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
                # Ignore malformed entries, keep the rest.
                continue

        return codes

    def _save_to_disk(self, codes: list[CodeEntry]) -> None:
        if self.cache_path is None:
            return
        data = [c.to_dict() for c in codes]
        try:
            self.cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            # Best-effort persistence; ignore IO errors.
            pass

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_codes(self) -> list[CodeEntry]:
        """Return all cached codes (including possibly expired ones).

        Results are backed by an internal in-memory list. Callers must not
        mutate the returned list in-place.
        """
        if not self._loaded:
            self._codes = self._load_from_disk()
            self._loaded = True
        # Return a shallow copy to avoid accidental in-place modification.
        return list(self._codes)

    def load(self) -> list[CodeEntry]:
        """Backward-compatible alias for `get_codes()`.

        Kept for existing callers; prefer `get_codes()` in new code.
        """
        return self.get_codes()

    def save(self, codes: list[CodeEntry]) -> None:
        """Persist codes to disk in JSON format and update in-memory cache."""
        self._codes = list(codes)
        self._loaded = True
        self._save_to_disk(self._codes)

    def purge(self) -> None:
        """Delete the cache file from disk and clear in-memory state."""
        self._codes = []
        self._loaded = True

        try:
            if self.cache_path is not None and self.cache_path.exists():
                self.cache_path.unlink()
        except Exception:
            # Ignore failures; cache will simply be considered empty.
            pass

    # ------------------------------------------------------------------ #
    # Refresh logic
    # ------------------------------------------------------------------ #

    def refresh(self, url: str, *, use_network: bool = True) -> list[CodeEntry]:
        """Fetch new codes, merge with cache, drop expired entries, save and return.

        - Existing cached codes are loaded (from memory or disk).
        - If ``use_network`` is True, fresh codes from the remote URL are fetched
          and merged by ``start_str``.
        - Codes whose ``end`` timestamp is earlier than "now" in ``self.tz``
          are discarded.
        """
        # Index existing codes by their canonical start timestamp string.
        existing: dict[str, CodeEntry] = {c.start_str: c for c in self.get_codes()}

        fresh: list[CodeEntry] = []
        if use_network:
            try:
                fresh = fetch_codes(url)
            except Exception:
                # Network / parsing errors -> treat as "no new codes".
                fresh = []

        for entry in fresh:
            existing[entry.start_str] = entry

        now_utc = datetime.now(self.tz)
        active = [c for c in existing.values() if c.end >= now_utc]

        # Keep entries ordered by start time for predictable behaviour.
        active.sort(key=lambda c: c.start)

        self.save(active)
        return active
