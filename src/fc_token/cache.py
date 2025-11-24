"""On-disk cache management for activation codes."""

from __future__ import annotations

import json
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QStandardPaths

from .models import CodeEntry, UTC
from .scraper import fetch_codes


class CodeCache:
    """Manage on-disk cache of activation codes with expiration filtering.

    All timestamps are stored and compared in UTC.
    """

    def __init__(self, app_name: str = "fc_token", *, tz: tzinfo = UTC) -> None:
        self.tz = tz

        cache_root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        if cache_root:
            base_path = Path(cache_root)
        else:
            # Fallback for environments where QStandardPaths returns an empty string.
            base_path = Path.home() / ".cache"

        self.cache_dir = base_path / app_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_path = self.cache_dir / "file_centipede_codes.json"

    # --------------------------------------------------------------------- #
    # Persistence helpers
    # --------------------------------------------------------------------- #

    def load(self) -> list[CodeEntry]:
        """Load cached codes from disk.

        Malformed entries are ignored.
        """
        if not self.cache_path.exists():
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

    def save(self, codes: list[CodeEntry]) -> None:
        """Persist codes to disk in JSON format."""
        data = [c.to_dict() for c in codes]
        try:
            self.cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            # Best-effort persistence; ignore IO errors.
            pass

    def purge(self) -> None:
        """Delete the cache file from disk."""
        try:
            if self.cache_path.exists():
                self.cache_path.unlink()
        except Exception:
            # Ignore failures; cache will simply be considered empty.
            pass

    # --------------------------------------------------------------------- #
    # Refresh logic
    # --------------------------------------------------------------------- #

    def refresh(self, url: str) -> list[CodeEntry]:
        """Fetch new codes, merge with cache, drop expired entries, save and return.

        - Existing cached codes are loaded.
        - Fresh codes from the remote URL are fetched and merged by `start_str`.
        - Codes whose `end` timestamp is earlier than "now" in `self.tz`
          are discarded.
        """
        # Index existing codes by their canonical start timestamp string.
        existing: dict[str, CodeEntry] = {c.start_str: c for c in self.load()}

        try:
            fresh = fetch_codes(url)
        except Exception:
            # Network / parsing errors -> treat as "no new codes".
            fresh = []

        for entry in fresh:
            existing[entry.start_str] = entry

        now_utc = datetime.now(self.tz)
        active = [c for c in existing.values() if c.end >= now_utc]

        # Keep entries ordered by start time for predictable behavior.
        active.sort(key=lambda c: c.start)

        self.save(active)
        return active
