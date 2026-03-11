"""Hardened source fetching for File Centipede activation codes."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import requests

from fc_token.config import BROWSER_IDENTITIES
from fc_token.models import CodeEntry, UTC
from fc_token.scraper import parse_codes

_REQUEST_TIMEOUT_SECONDS = 15


@dataclass(frozen=True, slots=True)
class SourceFetchResult:
    """Structured result for one source fetch."""

    codes: list[CodeEntry]
    identity_label: str
    raw_bytes: int
    fetched_at_utc: datetime
    url: str
    raw_text: str


class SourceFetchError(RuntimeError):
    """Base exception for source fetch failures."""


class SourceNetworkError(SourceFetchError):
    """The source could not be retrieved over the network."""


class SourceParseError(SourceFetchError):
    """The source was retrieved but did not contain usable activation codes."""


class ActivationSourceClient:
    """Fetch activation codes from the upstream HTML source."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        identities: Sequence[tuple[str, str]] | None = None,
        timeout_seconds: int = _REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._session = session or self._build_session()
        self._identities = list(identities or BROWSER_IDENTITIES)
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _build_session() -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        return session

    def _choose_identity(self) -> tuple[str, str]:
        if not self._identities:
            raise SourceFetchError("No browser identities are configured.")
        return random.choice(self._identities)

    def fetch_codes(self, url: str) -> SourceFetchResult:
        identity_label, user_agent = self._choose_identity()
        headers = {"User-Agent": user_agent}
        fetched_at_utc = datetime.now(UTC)
        try:
            response = self._session.get(url, headers=headers, timeout=self._timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SourceNetworkError(f"Could not retrieve activation page: {exc}") from exc

        raw_text = response.text
        raw_bytes = len(response.content or b"")
        codes = parse_codes(raw_text)
        if not codes:
            raise SourceParseError("Activation page did not contain any valid activation codes.")

        return SourceFetchResult(
            codes=codes,
            identity_label=identity_label,
            raw_bytes=raw_bytes,
            fetched_at_utc=fetched_at_utc,
            url=url,
            raw_text=raw_text,
        )
