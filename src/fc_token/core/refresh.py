"""Refresh orchestration and state machine for fc-token."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

from fc_token.models import CodeEntry, UTC

if TYPE_CHECKING:
    from fc_token.cache import CodeCache

from .source import ActivationSourceClient, SourceNetworkError, SourceParseError


class RefreshTrigger(str, Enum):
    INITIAL = "initial"
    AUTO = "auto"
    MANUAL = "manual"
    FORCED = "forced"


class RefreshStateKind(str, Enum):
    IDLE = "idle"
    USING_CACHE = "using_cache"
    REFRESHING = "refreshing"
    REFRESHED = "refreshed"
    NETWORK_FAILED = "network_failed"
    PARSE_FAILED = "parse_failed"


@dataclass(frozen=True, slots=True)
class RefreshState:
    kind: RefreshStateKind
    detail: str = ""
    used_network: bool = False
    last_error: str | None = None
    last_refresh_utc: datetime | None = None
    trigger: RefreshTrigger | None = None


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    codes: list[CodeEntry]
    fetched_at_utc: datetime | None
    state: RefreshState
    identity_label: str | None = None
    raw_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class RefreshDecision:
    should_use_network: bool
    next_allowed_utc: datetime | None
    reason: str


@dataclass(frozen=True, slots=True)
class RefreshPolicy:
    min_online_refresh_interval: timedelta = timedelta(hours=6)


@dataclass(slots=True)
class RefreshStateMachine:
    current: RefreshState = field(
        default_factory=lambda: RefreshState(kind=RefreshStateKind.IDLE, detail="Idle")
    )

    def start(self, *, use_network: bool, trigger: RefreshTrigger) -> RefreshState:
        detail = "Refreshing from network" if use_network else "Using cached activation codes"
        state = RefreshState(
            kind=RefreshStateKind.REFRESHING if use_network else RefreshStateKind.USING_CACHE,
            detail=detail,
            used_network=use_network,
            trigger=trigger,
            last_refresh_utc=self.current.last_refresh_utc,
        )
        self.current = state
        return state

    def finish(
        self,
        *,
        used_network: bool,
        trigger: RefreshTrigger,
        fetched_at_utc: datetime | None,
        detail: str,
    ) -> RefreshState:
        state = RefreshState(
            kind=RefreshStateKind.REFRESHED if used_network else RefreshStateKind.USING_CACHE,
            detail=detail,
            used_network=used_network,
            trigger=trigger,
            last_refresh_utc=fetched_at_utc or self.current.last_refresh_utc,
        )
        self.current = state
        return state

    def fail(
        self,
        *,
        kind: RefreshStateKind,
        trigger: RefreshTrigger,
        used_network: bool,
        detail: str,
        error: str,
        last_refresh_utc: datetime | None,
    ) -> RefreshState:
        state = RefreshState(
            kind=kind,
            detail=detail,
            used_network=used_network,
            trigger=trigger,
            last_error=error,
            last_refresh_utc=last_refresh_utc,
        )
        self.current = state
        return state


class RefreshService:
    """Coordinate when and how refreshes occur."""

    def __init__(
        self,
        cache: "CodeCache",
        *,
        policy: RefreshPolicy | None = None,
        source_client: ActivationSourceClient | None = None,
    ) -> None:
        self.cache = cache
        self.policy = policy or RefreshPolicy()
        self.source_client = source_client or ActivationSourceClient()
        self.state_machine = RefreshStateMachine()

    def decide_network_use(
        self,
        *,
        last_refresh_utc: datetime | None,
        force_network: bool = False,
    ) -> RefreshDecision:
        now_utc = datetime.now(UTC)
        if force_network:
            return RefreshDecision(True, None, "Forced network refresh requested.")

        active_codes = self.cache.get_active_codes(now=now_utc)
        if active_codes:
            return RefreshDecision(
                False,
                None,
                "Cached activation codes already cover the current period.",
            )

        if last_refresh_utc is None:
            return RefreshDecision(True, None, "No previous online refresh has been recorded.")

        next_allowed_utc = last_refresh_utc + self.policy.min_online_refresh_interval
        if now_utc < next_allowed_utc:
            return RefreshDecision(
                False,
                next_allowed_utc,
                "Minimum interval between online refreshes has not elapsed.",
            )

        return RefreshDecision(True, None, "Online refresh is allowed.")

    def load_cache_outcome(
        self,
        *,
        trigger: RefreshTrigger,
        last_refresh_utc: datetime | None,
    ) -> RefreshOutcome:
        now_utc = datetime.now(UTC)
        codes = self.cache.get_active_codes(now=now_utc)
        detail = "Using cached activation codes" if codes else "No cached activation codes available"
        state = self.state_machine.finish(
            used_network=False,
            trigger=trigger,
            fetched_at_utc=last_refresh_utc,
            detail=detail,
        )
        return RefreshOutcome(
            codes=codes,
            fetched_at_utc=None,
            state=state,
            identity_label=None,
            raw_bytes=None,
        )

    def refresh(
        self,
        url: str,
        *,
        trigger: RefreshTrigger,
        last_refresh_utc: datetime | None,
        force_network: bool = False,
        initial: bool = False,
    ) -> RefreshOutcome:
        del initial  # the UI uses this flag; refresh orchestration does not need it.

        decision = self.decide_network_use(
            last_refresh_utc=last_refresh_utc,
            force_network=force_network,
        )
        if not decision.should_use_network:
            return self.load_cache_outcome(trigger=trigger, last_refresh_utc=last_refresh_utc)

        self.state_machine.start(use_network=True, trigger=trigger)
        try:
            result = self.source_client.fetch_codes(url)
        except SourceParseError as exc:
            codes = self.cache.get_active_codes(now=datetime.now(UTC))
            state = self.state_machine.fail(
                kind=RefreshStateKind.PARSE_FAILED,
                trigger=trigger,
                used_network=True,
                detail="Activation source changed or returned unusable data",
                error=str(exc),
                last_refresh_utc=last_refresh_utc,
            )
            return RefreshOutcome(codes=codes, fetched_at_utc=None, state=state)
        except SourceNetworkError as exc:
            codes = self.cache.get_active_codes(now=datetime.now(UTC))
            state = self.state_machine.fail(
                kind=RefreshStateKind.NETWORK_FAILED,
                trigger=trigger,
                used_network=True,
                detail="Could not reach activation source",
                error=str(exc),
                last_refresh_utc=last_refresh_utc,
            )
            return RefreshOutcome(codes=codes, fetched_at_utc=None, state=state)

        self.cache.last_identity_used = result.identity_label
        self.cache.last_scrape_raw_bytes = result.raw_bytes
        self.cache.last_scraped_codes_count = len(result.codes)
        codes = self.cache.merge_and_save(result.codes, now=result.fetched_at_utc)
        state = self.state_machine.finish(
            used_network=True,
            trigger=trigger,
            fetched_at_utc=result.fetched_at_utc,
            detail=f"Fetched {len(result.codes)} activation code{'s' if len(result.codes) != 1 else ''}",
        )
        return RefreshOutcome(
            codes=codes,
            fetched_at_utc=result.fetched_at_utc,
            state=state,
            identity_label=result.identity_label,
            raw_bytes=result.raw_bytes,
        )
