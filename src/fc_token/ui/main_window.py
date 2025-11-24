from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QClipboard, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fc_token.cache import CodeCache
from fc_token.config import (
    DEFAULT_CODES_URL,
    DEFAULT_TIMEZONE,
)
from fc_token.icons import load_app_icon
from fc_token.models import CodeEntry
from fc_token.scraper import get_code_for_date
from fc_token.ui.dialogs.future_codes import show_future_codes_dialog
from fc_token.ui.utils import get_local_zone, make_code_view


class MainWindow(QMainWindow):
    """Main application window (without tray / scheduling logic).

    This refactored version no longer performs any network operations itself.
    Network refreshes are delegated to a background worker managed by the
    TrayController, which calls :meth:`refresh_from_codes` with the newly
    active list of codes.
    """

    def __init__(self, cache: CodeCache) -> None:
        super().__init__()
        self.setWindowTitle("File Centipede Activation Codes")

        self.cache = cache
        self.url: str = DEFAULT_CODES_URL

        # Cached codes from last refresh, used for the "Future codes" popup.
        self.future_codes: list[CodeEntry] = []

        # Track last known code string for change detection (tray uses this).
        self.last_code: str | None = None

        # Tray controller is attached later (for close-to-tray behavior).
        self._tray_controller = None

        self._setup_ui()
        self.resize(self.width(), 122)

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout()
        central.setLayout(layout)

        # Header row: label + small copy button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        self.current_label = QLabel("Current code:")
        self.current_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        header_row.addWidget(self.current_label)
        header_row.addStretch()

        self.copy_button = QPushButton()
        self.copy_button.setFixedSize(24, 24)
        self.copy_button.setToolTip("Copy current code")
        copy_icon = QIcon.fromTheme("edit-copy")
        if copy_icon.isNull():
            self.copy_button.setText("📋")
        else:
            self.copy_button.setIcon(copy_icon)
        self.copy_button.setFlat(True)
        self.copy_button.clicked.connect(self.copy_current_code)
        header_row.addWidget(self.copy_button)

        layout.addLayout(header_row)

        # Soft-wrapped view for the current code
        self.current_code_view = make_code_view(self)
        self.current_code_view.setMinimumHeight(60)
        layout.addWidget(self.current_code_view)

        # Future codes button (opens popup dialog)
        future_button = QPushButton("Future codes…")
        future_button.setToolTip("Show all cached activation codes")
        future_button.clicked.connect(self.show_future_codes)
        layout.addWidget(future_button)

        # Set the window icon to the app icon
        app_icon = load_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

    # ------------------------------------------------------------------ #
    # Integration with tray controller
    # ------------------------------------------------------------------ #

    def set_tray_controller(self, tray_controller) -> None:
        """Attach the tray controller so we can implement close-to-tray."""
        self._tray_controller = tray_controller

    # ------------------------------------------------------------------ #
    # Data / cache operations
    # ------------------------------------------------------------------ #

    def refresh_from_codes(
        self,
        codes: Sequence[CodeEntry],
        *,
        initial: bool = False,
    ) -> bool:
        """Update internal state and UI from a list of codes.

        Args:
            codes: The full list of active codes (typically from CodeCache).
            initial: True if this is the first refresh (suppresses change signal
                     when computing whether the code has changed).

        Returns:
            True if the active code changed (and both old/new exist).
        """
        self.future_codes = list(codes)

        current_code = self._get_current_code_from_list(self.future_codes)
        if current_code:
            self.current_code_view.setPlainText(current_code)
            self.current_label.setText("Current code:")
        else:
            self.current_code_view.clear()
            self.current_label.setText("Current code: None")

        old_code = self.last_code
        self.last_code = current_code

        if initial:
            return False

        if current_code and old_code and current_code != old_code:
            return True
        return False

    def refresh_from_cache(self, *, initial: bool = False) -> bool:
        """Load codes from the local cache and refresh the UI.

        This is a lightweight, offline-only operation that runs entirely in
        the GUI thread.
        """
        codes = self.cache.get_codes()
        return self.refresh_from_codes(codes, initial=initial)

    def _get_current_code_from_list(
        self,
        codes: Sequence[CodeEntry],
    ) -> str | None:
        """Return the code active for the current time (in UTC), if any.

        All internal validity windows are stored as UTC; we query with
        the current UTC timestamp and let the scraper logic match.
        """
        if not codes:
            return None

        now_utc = datetime.now(timezone.utc)
        return get_code_for_date(now_utc, list(codes))

    def get_current_code(self) -> str | None:
        """Public helper used by UI actions.

        Prefer the in-memory codes from the last refresh; fall back to a
        quick cache load if needed.
        """
        if self.future_codes:
            codes = self.future_codes
        else:
            codes = self.cache.get_codes()
        return self._get_current_code_from_list(codes)

    # ------------------------------------------------------------------ #
    # User actions
    # ------------------------------------------------------------------ #

    def show_future_codes(self) -> None:
        """Open the future-codes popup."""
        local_zone = get_local_zone(DEFAULT_TIMEZONE)
        show_future_codes_dialog(self, self.future_codes, local_zone)

    def copy_current_code(self) -> None:
        """Copy the current code to the clipboard."""
        code = self.get_current_code()
        if not code:
            QMessageBox.information(self, "Copy code", "No active code found.")
            return

        clipboard: QClipboard = QApplication.instance().clipboard()
        clipboard.setText(code, QClipboard.Mode.Clipboard)
        QMessageBox.information(self, "Copy code", "Current code copied to clipboard.")

    def purge_cache(self) -> None:
        """Clear the on-disk cache and reset the UI state."""
        reply = QMessageBox.question(
            self,
            "Purge cache",
            "Are you sure you want to delete the cached codes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.cache.purge()
        self.future_codes = []
        self.current_code_view.clear()
        self.current_label.setText("Current code: None (cache purged)")
        self.last_code = None

    # ------------------------------------------------------------------ #
    # Window behavior
    # ------------------------------------------------------------------ #

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Close to tray if a tray controller is present."""
        if (
            self._tray_controller is not None
            and self._tray_controller.is_tray_visible()
        ):
            event.ignore()
            self.hide()
            self._tray_controller.notify_hidden_to_tray()
        else:
            super().closeEvent(event)
