"""On-disk cache management for activation codes."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List

from PyQt6.QtCore import QStandardPaths

from .models import CodeEntry
from .scraper import fetch_codes


class CodeCache:
    """Manage on-disk cache of activation codes with expiration filtering."""

    def __init__(self, app_name: str = "fc_token") -> None:
        cache_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        if not cache_dir:
            cache_dir = os.path.join(os.path.expanduser("~"), ".cache")
        self.cache_dir = os.path.join(cache_dir, app_name)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_path = os.path.join(self.cache_dir, "file_centipede_codes.json")

    def load(self) -> List[CodeEntry]:
        if not os.path.exists(self.cache_path):
            return []
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return []

        out: List[CodeEntry] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                start_str = item["start_date"]
                end_str = item["end_date"]
                code = str(item["code"])
                start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            out.append(CodeEntry(start=start, end=end, code=code))
        return out

    def save(self, codes: List[CodeEntry]) -> None:
        data = [
            {
                "start_date": c.start_str,
                "end_date": c.end_str,
                "code": c.code,
            }
            for c in codes
        ]
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def purge(self) -> None:
        try:
            if os.path.exists(self.cache_path):
                os.remove(self.cache_path)
        except Exception:
            pass

    def refresh(self, url: str) -> List[CodeEntry]:
        """Fetch new codes, merge with cache, drop expired entries, save and return."""
        existing = {c.start_str: c for c in self.load()}
        try:
            fresh = fetch_codes(url)
        except Exception:
            fresh = []
        for entry in fresh:
            existing[entry.start_str] = entry

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        active = [c for c in existing.values() if c.end >= now_utc]
        active.sort(key=lambda c: c.start)
        self.save(active)
        return active
