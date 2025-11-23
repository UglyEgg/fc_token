"""Data models used by fc-token."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CodeEntry:
    """Single activation code with validity window."""

    start: datetime
    end: datetime
    code: str

    @property
    def start_str(self) -> str:
        return self.start.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def end_str(self) -> str:
        return self.end.strftime("%Y-%m-%d %H:%M:%S")

    def display_line(self) -> str:
        return f"{self.start_str} – {self.end_str} :: {self.code}"
