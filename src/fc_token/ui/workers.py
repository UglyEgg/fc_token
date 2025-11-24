"""Background worker objects used by the fc-token UI.

Currently provides:
- RefreshWorker: runs CodeCache.refresh(...) off the GUI thread and emits
  a list of CodeEntry objects (or an error string) when complete.
"""

from __future__ import annotations

from typing import List

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from fc_token.cache import CodeCache
from fc_token.models import CodeEntry


class RefreshWorker(QObject):
    """Worker that refreshes activation codes in a background thread.

    Signals:
        finished(list[CodeEntry]): emitted on success with the active codes.
        error(str): emitted if an exception is raised during refresh.
    """

    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, cache: CodeCache, url: str, *, use_network: bool = True) -> None:
        super().__init__()
        self._cache = cache
        self._url = url
        self._use_network = use_network

    @pyqtSlot()
    def run(self) -> None:
        try:
            codes: List[CodeEntry] = self._cache.refresh(
                self._url,
                use_network=self._use_network,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.error.emit(str(exc))
        else:
            self.finished.emit(codes)
