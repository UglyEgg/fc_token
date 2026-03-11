"""Background worker objects used by the fc-token UI."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from fc_token.core.refresh import RefreshOutcome, RefreshService, RefreshTrigger


class RefreshWorker(QObject):
    """Worker that runs refresh orchestration off the GUI thread."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        refresh_service: RefreshService,
        url: str,
        *,
        trigger: RefreshTrigger,
        last_refresh_utc: datetime | None,
        force_network: bool = False,
        initial: bool = False,
    ) -> None:
        super().__init__()
        self._refresh_service = refresh_service
        self._url = url
        self._trigger = trigger
        self._last_refresh_utc = last_refresh_utc
        self._force_network = force_network
        self._initial = initial

    @pyqtSlot()
    def run(self) -> None:
        try:
            outcome: RefreshOutcome = self._refresh_service.refresh(
                self._url,
                trigger=self._trigger,
                last_refresh_utc=self._last_refresh_utc,
                force_network=self._force_network,
                initial=self._initial,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.error.emit(str(exc))
        else:
            self.finished.emit(outcome)
