"""Data models used by fc-token."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from typing import Any, Self

# All codes are treated as UTC internally.
UTC: tzinfo = timezone.utc


@dataclass(frozen=True, slots=True)
class CodeEntry:
    """Single activation code with validity window.

    All `start` / `end` datetimes are expected to be timezone-aware and in UTC.
    """

    start: datetime
    end: datetime
    code: str

    @property
    def start_str(self) -> str:
        """Start timestamp in canonical string format (UTC)."""
        return self.start.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

    @property
    def end_str(self) -> str:
        """End timestamp in canonical string format (UTC)."""
        return self.end.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

    def display_line(self) -> str:
        """Human-readable one-line representation."""
        return f"{self.start_str} – {self.end_str} :: {self.code}"

    def contains(self, moment: datetime) -> bool:
        """Return True if *moment* is within this entry's validity window.

        `moment` may be naive (treated as UTC) or aware (any tz).
        """
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        else:
            moment = moment.astimezone(UTC)

        start = (
            self.start
            if self.start.tzinfo is not None
            else self.start.replace(tzinfo=UTC)
        )
        end = self.end if self.end.tzinfo is not None else self.end.replace(tzinfo=UTC)
        return start <= moment <= end

    # --- JSON / dict helpers -------------------------------------------------

    def to_dict(self) -> dict[str, str]:
        """Serialize this entry to a JSON-friendly dict."""
        return {
            "start_date": self.start_str,
            "end_date": self.end_str,
            "code": self.code,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, tz: tzinfo = UTC) -> Self:
        """Create an entry from a dict as stored in the cache.

        Expected keys:
            - "start_date": "YYYY-mm-dd HH:MM:SS" (UTC)
            - "end_date":   "YYYY-mm-dd HH:MM:SS" (UTC)
            - "code":       string
        """
        start_str = str(data["start_date"])
        end_str = str(data["end_date"])
        code = str(data["code"])

        start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
        end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)

        return cls(start=start, end=end, code=code)
