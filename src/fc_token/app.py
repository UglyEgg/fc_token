"""KDE/Plasma-friendly tray application for File Centipede activation codes.

Refactored app using modular structure:

    fc_token/
      config.py
      models.py
      scraper.py
      cache.py
      icons.py
      app.py  (this file)

This file handles only UI, tray logic, and integration glue.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from PyQt6.QtCore import QTimer, Qt, QSettings
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QClipboard,
    QFont,
    QIcon,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from zoneinfo import ZoneInfo

from .cache import CodeCache
from .config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_CODES_URL,
    DEFAULT_TIMEZONE,
    FILE_CENTIPEDE_BUY_URL,
    FILE_CENTIPEDE_URL,
    KEY_AUTO_REFRESH,
    KEY_ICON_MODE,
    KEY_REFRESH_INTERVAL,
    SETTINGS_APP,
    SETTINGS_ORG,
)
from .icons import (
    create_attention_icon,
    is_dark_theme,
    load_app_icon,
    load_tray_base_icon,
    recolor_icon,
)
from .models import CodeEntry
from .scraper import get_code_for_date


class MainWindow(QMainWindow):
    """Main application window with tray integration."""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("File Centipede Activation Codes")

        self.cache = CodeCache()
        self.url = DEFAULT_CODES_URL
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        # Track last known code for change detection
        self.last_code: Optional[str] = None
        self.unseen_change: bool = False

        # Icon mode: "auto", "light", "dark"
        self.icon_mode: str = self.settings.value(KEY_ICON_MODE, "auto", type=str)

        # Cache of last refresh's codes for the "Future codes" popup
        self.future_codes: List[CodeEntry] = []

        # Refresh interval (in minutes)
        self.refresh_interval_minutes: int = self.settings.value(
            KEY_REFRESH_INTERVAL, 60, type=int
        )

        # Automatic interval based on code expiry
        self.interval_auto_enabled: bool = self.settings.value(
            "interval_auto", False, type=bool
        )

        # Next scheduled refresh (UTC)
        self.next_refresh_deadline: Optional[datetime] = None

        # --- Build UI ---
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout()
        central.setLayout(layout)

        # Current code header row: label + small copy button
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
        self.current_code_view = QTextEdit()
        self.current_code_view.setReadOnly(True)
        # Wrap tokens cleanly, treat as monospaced block
        self.current_code_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.current_code_view.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        code_font: QFont = self.current_code_view.font()
        code_font.setFamily("Monospace")
        self.current_code_view.setFont(code_font)
        self.current_code_view.setMinimumHeight(60)
        layout.addWidget(self.current_code_view)

        # Future codes button (opens popup dialog)
        future_button = QPushButton("Future codes…")
        future_button.setToolTip("Show all cached activation codes")
        future_button.clicked.connect(self.show_future_codes)
        layout.addWidget(future_button)

        # Auto-refresh enabled flag
        self.auto_refresh_enabled = self.settings.value(
            KEY_AUTO_REFRESH, True, type=bool
        )

        # Timer for scheduled refresh, and a separate countdown updater
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_refresh_timer)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_refresh_ui)

        # --- System tray integration ---
        self.tray_icon = QSystemTrayIcon(self)

        # Build tray icon variants
        base_mono = load_tray_base_icon()
        self.tray_icon_dark = recolor_icon(base_mono, QColor(0, 0, 0))
        self.tray_icon_light = recolor_icon(base_mono, QColor(255, 255, 255))
        self.attention_tray_icon_dark = create_attention_icon(self.tray_icon_dark)
        self.attention_tray_icon_light = create_attention_icon(self.tray_icon_light)

        # Set the window icon to the app icon
        self.setWindowIcon(load_app_icon())

        # Tray menu
        tray_menu = QMenu()

        # Next refresh label at top
        self.action_next_refresh = QAction("Next refresh: n/a", self)
        self.action_next_refresh.setEnabled(False)
        tray_menu.addAction(self.action_next_refresh)

        tray_menu.addSeparator()

        # Top-level quick action
        self.action_show = QAction("Show window", self)
        self.action_show.triggered.connect(self.show_normal_from_tray)
        tray_menu.addAction(self.action_show)

        tray_menu.addSeparator()

        # Actions submenu
        actions_menu = tray_menu.addMenu("Actions")

        self.action_refresh = QAction("Refresh now", self)
        self.action_refresh.triggered.connect(self.refresh_codes)
        actions_menu.addAction(self.action_refresh)

        self.action_purge = QAction("Purge cache", self)
        self.action_purge.triggered.connect(self.purge_cache)
        actions_menu.addAction(self.action_purge)

        tray_menu.addSeparator()

        # Settings submenu
        settings_menu = tray_menu.addMenu("Settings")

        # Auto-refresh toggle
        self.action_auto_refresh = QAction("Auto-refresh", self)
        self.action_auto_refresh.setCheckable(True)
        self.action_auto_refresh.setChecked(self.auto_refresh_enabled)
        self.action_auto_refresh.toggled.connect(self.toggle_auto_refresh)
        settings_menu.addAction(self.action_auto_refresh)

        # Refresh interval dialog action
        self.action_change_interval = QAction("Refresh interval…", self)
        self.action_change_interval.triggered.connect(self.change_refresh_interval)
        settings_menu.addAction(self.action_change_interval)

        # Interval summary (non-interactive)
        self.action_interval_summary = QAction("", self)
        self.action_interval_summary.setEnabled(False)
        settings_menu.addAction(self.action_interval_summary)

        # Tray icon theme submenu
        icon_theme_menu = settings_menu.addMenu("Tray icon theme")

        icon_group = QActionGroup(self)
        icon_group.setExclusive(True)

        self.action_icon_auto = QAction("Auto", self, checkable=True)
        self.action_icon_light = QAction("Light", self, checkable=True)
        self.action_icon_dark = QAction("Dark", self, checkable=True)

        icon_group.addAction(self.action_icon_auto)
        icon_group.addAction(self.action_icon_light)
        icon_group.addAction(self.action_icon_dark)

        icon_theme_menu.addAction(self.action_icon_auto)
        icon_theme_menu.addAction(self.action_icon_light)
        icon_theme_menu.addAction(self.action_icon_dark)

        # Set current selection
        if self.icon_mode == "light":
            self.action_icon_light.setChecked(True)
        elif self.icon_mode == "dark":
            self.action_icon_dark.setChecked(True)
        else:
            self.action_icon_auto.setChecked(True)
            self.icon_mode = "auto"

        self.action_icon_auto.triggered.connect(lambda: self.set_icon_mode("auto"))
        self.action_icon_light.triggered.connect(lambda: self.set_icon_mode("light"))
        self.action_icon_dark.triggered.connect(lambda: self.set_icon_mode("dark"))

        # Autostart toggle (KDE / freedesktop autostart)
        self.action_autostart = QAction("Start on login", self)
        self.action_autostart.setCheckable(True)
        self.action_autostart.setChecked(self.is_autostart_enabled())
        self.action_autostart.toggled.connect(self.set_autostart_enabled)
        settings_menu.addAction(self.action_autostart)

        # Uninstall per-user launcher/icons
        self.action_uninstall = QAction("Remove launcher && icons (user)", self)
        self.action_uninstall.triggered.connect(self.uninstall_integration)
        settings_menu.addAction(self.action_uninstall)

        # --- About + Quit on root menu ---
        tray_menu.addSeparator()

        self.action_about = QAction("About…", self)
        self.action_about.triggered.connect(self.show_about)
        tray_menu.addAction(self.action_about)

        tray_menu.addSeparator()

        self.action_quit = QAction("Quit", self)
        self.action_quit.triggered.connect(self.quit_from_tray)
        tray_menu.addAction(self.action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)

        # Initial icon and refresh UI
        self.update_tray_icon()

        # Start timer and tooltip according to current settings
        self.update_timer()

        # Show tray icon last
        self.tray_icon.show()

        # Initial load (does NOT trigger a "code changed" notification)
        self.refresh_codes(initial=True)

    # --- Convenience helpers ---

    def info(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)

    def ask_yes_no(self, title: str, text: str) -> bool:
        reply = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    # --- Formatting helpers ---

    def _format_interval_minutes(self, minutes: int) -> str:
        days = minutes // (24 * 60)
        hours = (minutes // 60) % 24
        mins = minutes % 60
        parts: List[str] = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if mins and not days and not hours:
            # only show minutes if there are no larger units
            parts.append(f"{mins}m")
        if not parts:
            return "0m"
        return " ".join(parts)

    def _format_interval_seconds(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        minutes = max(1, seconds // 60)
        return self._format_interval_minutes(minutes)

    # --- Refresh / tooltip / menu sync ---

    def update_refresh_ui(self) -> None:
        """Update tray tooltip, next-refresh menu item, and interval summary."""
        now_utc = datetime.now(timezone.utc)

        # Interval summary
        self.action_interval_summary.setText(
            f"Current interval: {self._format_interval_minutes(self.refresh_interval_minutes)}"
        )

        # Next refresh label + tooltip
        lines = [APP_NAME]
        next_text = "Next refresh: n/a"

        if self.auto_refresh_enabled and self.refresh_interval_minutes > 0:
            lines.append(
                f"Auto-refresh: every {self._format_interval_minutes(self.refresh_interval_minutes)}"
            )
            if self.next_refresh_deadline is not None:
                remaining = (self.next_refresh_deadline - now_utc).total_seconds()
                if remaining < 0:
                    remaining = 0
                human = self._format_interval_seconds(int(remaining))
                lines.append(f"Next refresh in {human}")
                next_text = f"Next refresh in: {human}"
            else:
                next_text = "Next refresh: scheduled"
        else:
            lines.append("Auto-refresh: disabled")

        self.tray_icon.setToolTip("\n".join(lines))
        self.action_next_refresh.setText(next_text)

    # --- Tray behaviors ---

    def show_normal_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Left-click toggles window visibility
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_normal_from_tray()

    def toggle_auto_refresh(self, enabled: bool) -> None:
        self.auto_refresh_enabled = enabled
        self.settings.setValue(KEY_AUTO_REFRESH, enabled)
        self.update_timer()
        self.tray_icon.showMessage(
            "File Centipede",
            "Auto-refresh enabled." if enabled else "Auto-refresh disabled.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def set_icon_mode(self, mode: str) -> None:
        """Set tray icon appearance mode ("auto", "light", "dark")."""
        if mode not in {"auto", "light", "dark"}:
            mode = "auto"
        self.icon_mode = mode
        self.settings.setValue(KEY_ICON_MODE, mode)
        self.update_tray_icon()

    def update_tray_icon(self) -> None:
        """Choose the right tray icon variant based on icon_mode/theme and change flag."""
        dark_theme = is_dark_theme()
        if self.icon_mode == "light":
            base = self.tray_icon_light
            attention = self.attention_tray_icon_light
        elif self.icon_mode == "dark":
            base = self.tray_icon_dark
            attention = self.attention_tray_icon_dark
        else:
            if dark_theme:
                base = self.tray_icon_light
                attention = self.attention_tray_icon_light
            else:
                base = self.tray_icon_dark
                attention = self.attention_tray_icon_dark

        icon = attention if self.unseen_change else base
        if icon and not icon.isNull():
            self.tray_icon.setIcon(icon)

    def quit_from_tray(self) -> None:
        self.refresh_timer.stop()
        self.countdown_timer.stop()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Close to tray: closing the window just hides it but keeps the tray running."""
        if self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "File Centipede",
                "Still running in the system tray. Use the tray icon menu to quit.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        else:
            super().closeEvent(event)

    # --- Scheduling + code-change handling ---

    def _compute_auto_interval(self) -> tuple[int, datetime]:
        """Compute automatic refresh interval based on last code expiry.

        If there are future codes, schedule a refresh for one day before the
        last code expires. If there are no future codes, refresh daily until
        new codes appear.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        codes = self.cache.load()
        future = [c for c in codes if c.end >= now]

        if future:
            last_end = max(c.end for c in future)
            target = last_end - timedelta(days=1)
            if target <= now:
                target = now + timedelta(minutes=5)
            delta_min = max(1, int((target - now).total_seconds() // 60))
            deadline = datetime.now(timezone.utc) + timedelta(minutes=delta_min)
            return delta_min, deadline

        # No future codes: default to daily checks
        delta_min = 24 * 60
        deadline = datetime.now(timezone.utc) + timedelta(days=1)
        return delta_min, deadline

    def update_timer(self) -> None:
        """Reconfigure timers based on current settings."""
        self.refresh_timer.stop()
        self.countdown_timer.stop()
        self.next_refresh_deadline = None

        if not self.auto_refresh_enabled:
            self.update_refresh_ui()
            return

        if self.interval_auto_enabled:
            interval_min, deadline = self._compute_auto_interval()
            self.refresh_interval_minutes = interval_min
            self.settings.setValue(KEY_REFRESH_INTERVAL, interval_min)
            self.next_refresh_deadline = deadline
        else:
            interval_min = max(1, int(self.refresh_interval_minutes))
            self.refresh_interval_minutes = interval_min
            self.settings.setValue(KEY_REFRESH_INTERVAL, interval_min)
            self.next_refresh_deadline = datetime.now(timezone.utc) + timedelta(
                minutes=interval_min
            )

        interval_ms = self.refresh_interval_minutes * 60 * 1000
        self.refresh_timer.start(interval_ms)
        # Update countdown every 60 seconds
        self.countdown_timer.start(60 * 1000)
        self.update_refresh_ui()

    def _on_refresh_timer(self) -> None:
        self.refresh_codes(initial=False)
        # Schedule next deadline for manual mode
        if not self.interval_auto_enabled and self.auto_refresh_enabled:
            self.next_refresh_deadline = datetime.now(timezone.utc) + timedelta(
                minutes=self.refresh_interval_minutes
            )
        self.update_refresh_ui()

    def refresh_codes(self, initial: bool = False) -> None:
        active = self.cache.refresh(self.url)
        self.future_codes = active

        current_code = self.get_current_code()
        if current_code:
            self.current_code_view.setPlainText(current_code)
        else:
            self.current_code_view.clear()

        old_code = self.last_code
        self.last_code = current_code

        if not initial and current_code and old_code and current_code != old_code:
            self._on_code_changed(current_code)

        # If auto interval is enabled, recompute schedule based on new codes
        if self.auto_refresh_enabled and self.interval_auto_enabled:
            self.update_timer()
        else:
            self.update_refresh_ui()

    def _on_code_changed(self, new_code: str) -> None:
        self.unseen_change = True
        self.update_tray_icon()
        self.tray_icon.showMessage(
            "Activation code updated",
            "A new File Centipede activation code is available.",
            QSystemTrayIcon.MessageIcon.Information,
            8000,
        )

    # --- Refresh interval dialog ---

    def change_refresh_interval(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Set refresh interval")
        lay = QVBoxLayout(dlg)

        auto_cb = QCheckBox("Automatically schedule based on code expiry")
        auto_cb.setChecked(self.interval_auto_enabled)
        lay.addWidget(auto_cb)

        total = self.refresh_interval_minutes
        days = total // (60 * 24)
        hours = (total // 60) % 24

        # Days
        row_days = QHBoxLayout()
        lbl_days = QLabel("Days:")
        spin_days = QSpinBox()
        spin_days.setRange(0, 365)
        spin_days.setValue(days)
        row_days.addWidget(lbl_days)
        row_days.addWidget(spin_days)
        lay.addLayout(row_days)

        # Hours
        row_hours = QHBoxLayout()
        lbl_hours = QLabel("Hours:")
        spin_hours = QSpinBox()
        spin_hours.setRange(0, 23)
        spin_hours.setValue(hours)
        row_hours.addWidget(lbl_hours)
        row_hours.addWidget(spin_hours)
        lay.addLayout(row_hours)

        def update_enabled(state: bool) -> None:
            enabled = not state
            spin_days.setEnabled(enabled)
            spin_hours.setEnabled(enabled)

        update_enabled(auto_cb.isChecked())
        auto_cb.toggled.connect(update_enabled)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if auto_cb.isChecked():
            self.interval_auto_enabled = True
            self.settings.setValue("interval_auto", True)
            self.update_timer()
            return

        # Manual interval from days + hours only
        total_minutes = spin_days.value() * 24 * 60 + spin_hours.value() * 60
        if total_minutes < 1:
            total_minutes = 1

        self.interval_auto_enabled = False
        self.settings.setValue("interval_auto", False)
        self.refresh_interval_minutes = total_minutes
        self.settings.setValue(KEY_REFRESH_INTERVAL, total_minutes)
        self.update_timer()

    # --- Future codes popup ---

    def show_future_codes(self) -> None:
        if not self.future_codes:
            self.info(
                "Future codes", "There are no cached activation codes to display."
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Future activation codes")
        layout = QVBoxLayout(dialog)

        table = QTableWidget(dialog)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Start", "End"])
        table.setRowCount(len(self.future_codes))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Use local timezone for display
        tz_name = os.environ.get("TIMEZONE") or DEFAULT_TIMEZONE
        try:
            local_zone = ZoneInfo(tz_name)
        except Exception:
            local_zone = timezone.utc

        for row, entry in enumerate(self.future_codes):
            start_local = entry.start.replace(tzinfo=timezone.utc).astimezone(
                local_zone
            )
            end_local = entry.end.replace(tzinfo=timezone.utc).astimezone(local_zone)
            start_str = start_local.strftime("%Y-%m-%d %H:%M")
            end_str = end_local.strftime("%Y-%m-%d %H:%M")
            table.setItem(row, 0, QTableWidgetItem(start_str))
            table.setItem(row, 1, QTableWidgetItem(end_str))

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(table)

        def open_entry(row: int, _column: int) -> None:
            if row < 0 or row >= len(self.future_codes):
                return
            entry = self.future_codes[row]

            dlg2 = QDialog(dialog)
            dlg2.setWindowTitle("Activation code")
            v = QVBoxLayout(dlg2)

            text = QTextEdit()
            text.setReadOnly(True)
            text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            text.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
            code_font2: QFont = text.font()
            code_font2.setFamily("Monospace")
            text.setFont(code_font2)
            text.setPlainText(entry.code)
            v.addWidget(text)

            close_btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            close_btns.accepted.connect(dlg2.accept)
            close_btns.rejected.connect(dlg2.reject)
            v.addWidget(close_btns)

            dlg2.exec()

        table.cellClicked.connect(open_entry)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=dialog)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)

        dialog.exec()

    # --- Cache + current code helpers ---

    def purge_cache(self) -> None:
        if not self.ask_yes_no(
            "Purge cache", "Are you sure you want to delete the cached codes?"
        ):
            return
        self.cache.purge()
        self.future_codes = []
        self.current_code_view.clear()
        self.current_label.setText("Current code: None (cache purged)")
        self.last_code = None
        self.unseen_change = False
        self.update_tray_icon()
        self.update_refresh_ui()

    def get_current_code(self) -> Optional[str]:
        codes = self.cache.load()
        if not codes:
            return None
        tz_name = os.environ.get("TIMEZONE") or DEFAULT_TIMEZONE
        try:
            local_zone = ZoneInfo(tz_name)
        except Exception:
            from datetime import timezone as _tz

            local_zone = _tz.utc
        now_local = datetime.now(local_zone)
        now_utc = now_local.astimezone(timezone.utc).replace(tzinfo=None)
        return get_code_for_date(now_utc, codes)

    def copy_current_code(self) -> None:
        code = self.get_current_code()
        if not code:
            self.info("Copy code", "No active code found.")
            return
        clipboard: QClipboard = QApplication.instance().clipboard()
        clipboard.setText(code, QClipboard.Mode.Clipboard)
        self.info("Copy code", "Current code copied to clipboard.")
        self.unseen_change = False
        self.update_tray_icon()

    # --- Autostart helpers ---

    def _autostart_desktop_path(self) -> str:
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return os.path.join(config_home, "autostart", "fc_token.desktop")

    def is_autostart_enabled(self) -> bool:
        return os.path.exists(self._autostart_desktop_path())

    def set_autostart_enabled(self, enabled: bool) -> None:
        path = self._autostart_desktop_path()
        autostart_dir = os.path.dirname(path)
        if enabled:
            os.makedirs(autostart_dir, exist_ok=True)
            desktop_content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={APP_NAME}\n"
                "Exec=fc-token\n"
                "Icon=fc_token\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(desktop_content)
            except Exception:
                pass
        else:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    # --- Install / uninstall integration ---

    def show_about(self) -> None:
        app_icon = load_app_icon()
        text = (
            f"<h3>{APP_NAME}</h3>"
            f"<p>Version {APP_VERSION}</p>"
            "<p>"
            "This helper fetches and manages the File Centipede trial activation codes "
            "and presents them in a KDE/Plasma-friendly tray application."
            "</p>"
            f"<p><b>File Centipede:</b> "
            f'<a href="{FILE_CENTIPEDE_URL}">{FILE_CENTIPEDE_URL}</a><br/>'
            f"<b>Project page:</b> <i>Not set</i></p>"
            f'<p><b><a href="{FILE_CENTIPEDE_BUY_URL}">Buy File Centipede</a></b></p>'
        )

        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        if not app_icon.isNull():
            box.setIconPixmap(app_icon.pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def uninstall_integration(self) -> None:
        """Remove .desktop file and icons installed for the current user."""
        if not self.ask_yes_no(
            "Remove integration",
            "Remove the .desktop launcher and icons installed for this user?",
        ):
            return

        data_home = os.environ.get(
            "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
        )
        apps_dir = os.path.join(data_home, "applications")
        icons_base = os.path.join(data_home, "icons", "hicolor")

        paths = [
            os.path.join(apps_dir, "fc_token.desktop"),
            os.path.join(icons_base, "scalable", "apps", "fc_token-symbolic.svg"),
            os.path.join(icons_base, "256x256", "apps", "fc_token.png"),
        ]

        removed_any = False
        for p in paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
                    removed_any = True
            except Exception:
                pass

        if removed_any:
            self.info("Removed", "Launcher and/or icons removed for this user.")
        else:
            self.info("Nothing to remove", "No installed launcher or icons were found.")


def main() -> int:
    """Application entry point."""
    # Simple CLI flags before Qt starts
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0

    if "--self-test" in sys.argv:
        try:
            app = QApplication(sys.argv)
            app.setQuitOnLastWindowClosed(False)

            app_icon = load_app_icon()
            if not app_icon.isNull():
                app.setWindowIcon(app_icon)

            app.setDesktopFileName("fc_token")

            win = MainWindow()
            win.hide()
            return 0
        except Exception as e:
            print(f"fc-token self-test failed: {e}", file=sys.stderr)
            return 1

    # Normal GUI run
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    app.setDesktopFileName("fc_token")

    win = MainWindow()
    win.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
