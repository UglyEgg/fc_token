from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from typing import Sequence

from PyQt6.QtCore import Qt, QEvent
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
from fc_token.icons import load_app_icon, is_dark_theme
from fc_token.models import CodeEntry
from fc_token.scraper import get_code_for_date
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

        # Cached codes from last refresh; used for the current code and
        # cached coverage summary.
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

        # Cached coverage summary (local dates only, no token values)
        self.coverage_label = QLabel()
        self.coverage_label.setObjectName("coverageLabel")
        self.coverage_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.coverage_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.coverage_label.setText("No activation codes cached yet.")

        # Apply theme-aware styling
        self._apply_coverage_label_palette()

        layout.addWidget(self.coverage_label)

        # Set the window icon to the app icon
        app_icon = load_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

    def _apply_coverage_label_palette(self) -> None:
        """Apply a readable, theme-aware color to the coverage label.

        KDE/Qt palette roles can be too dark on some Plasma themes, so we use
        hand-tuned high-contrast values instead.
        """
        if not hasattr(self, "coverage_label"):
            return

        if is_dark_theme():
            # Bright but not pure white – highly legible on dark backgrounds
            color = "#DDDDDD"
        else:
            # Dark grey that's readable but not harsh on light themes
            color = "#444444"

        self.coverage_label.setStyleSheet(f"color: {color}; font-size: 9pt;")

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
        self._update_coverage_summary()

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

    def _update_coverage_summary(self) -> None:
        """Update the cached coverage label using local dates only.

        This intentionally exposes *only* date ranges (no token values and no
        precise timestamps) so that the user can see roughly how far into the
        past/future their cached activation coverage extends, without revealing
        any additional secrets. The actual token values remain visible only via
        the Developer menu.
        """
        if not hasattr(self, "coverage_label"):
            # UI not initialised yet (defensive; should not normally happen).
            return

        if not self.future_codes:
            self.coverage_label.setText("No activation codes cached yet.")
            self.coverage_label.setToolTip("")
            return

        local_zone = get_local_zone(DEFAULT_TIMEZONE)

        # Convert to local dates and merge into contiguous ranges.
        date_ranges: list[tuple[date, date]] = []
        for entry in sorted(self.future_codes, key=lambda c: c.start):
            start_local = entry.start.astimezone(local_zone).date()
            end_local = entry.end.astimezone(local_zone).date()
            if not date_ranges:
                date_ranges.append((start_local, end_local))
                continue

            cur_start, cur_end = date_ranges[-1]
            # If this block starts before or exactly one day after the previous
            # block ends, merge them into a single range.
            if start_local <= (cur_end + timedelta(days=1)):
                if end_local > cur_end:
                    date_ranges[-1] = (cur_start, end_local)
            else:
                date_ranges.append((start_local, end_local))

        # Aggregate overall coverage + total days.
        overall_start = date_ranges[0][0]
        overall_end = date_ranges[-1][1]

        total_days = 0
        for start_d, end_d in date_ranges:
            total_days += (end_d - start_d).days + 1

        ranges_count = len(date_ranges)
        days_label = "day" if total_days == 1 else "days"
        ranges_label = "range" if ranges_count == 1 else "ranges"

        summary = (
            f"Cached activation coverage (local dates): "
            f"{overall_start.isoformat()} → {overall_end.isoformat()}  • "
            f"{total_days} {days_label} across {ranges_count} {ranges_label}"
        )
        self.coverage_label.setText(summary)

        # Detailed breakdown as a tooltip (dates only, still no token values).
        tooltip_lines = ["Cached ranges (local dates):"]
        for idx, (start_d, end_d) in enumerate(date_ranges, start=1):
            days = (end_d - start_d).days + 1
            tooltip_lines.append(
                f"  {idx}. {start_d.isoformat()} → {end_d.isoformat()}  ({days} days)"
            )
        self.coverage_label.setToolTip("\n".join(tooltip_lines))

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
        self._update_coverage_summary()
        self.current_code_view.clear()
        self.current_label.setText("Current code: None (cache purged)")
        self.last_code = None

    # ------------------------------------------------------------------ #
    # Window / palette behavior
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

    def changeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        """Respond to palette/theme changes to keep coverage label readable."""
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            self._apply_coverage_label_palette()
        super().changeEvent(event)
