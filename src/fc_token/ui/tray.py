from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtGui import QAction, QColor, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from fc_token.cache import CodeCache
from fc_token.config import (
    APP_NAME,
    KEY_AUTO_REFRESH,
    KEY_ICON_MODE,
    KEY_TIMEZONE,
    SETTINGS_APP,
    SETTINGS_ORG,
    DEFAULT_TIMEZONE,
)
from fc_token.icons import (
    create_attention_icon,
    is_dark_theme,
    load_app_icon,
    load_tray_base_icon,
    recolor_icon,
)
from fc_token.ui.dialogs.about import show_about_dialog
from fc_token.ui.dialogs.timezone import run_timezone_dialog
from fc_token.ui.utils import get_local_zone_name, get_local_zone


# Minimum allowed refresh interval (minutes) between *online* scrapes.
# Global anti-abuse floor: 6 hours.
MIN_REFRESH_MINUTES = 360

# Auto-refresh schedule: once per day (used for the timer / "Next" info).
AUTO_REFRESH_MINUTES = 24 * 60


class TrayController:
    """System tray integration, scheduling, and notifications."""

    def __init__(self, window, cache: CodeCache) -> None:
        self.window = window
        self.cache = cache

        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        # Icon mode: "auto", "light", "dark"
        self.icon_mode: str = self.settings.value(KEY_ICON_MODE, "auto", type=str)

        # Auto-refresh enabled flag (daily when enabled)
        self.auto_refresh_enabled: bool = self.settings.value(
            KEY_AUTO_REFRESH, True, type=bool
        )

        # Whether the main window should be shown when the app starts.
        # Default: True (show on start).
        self.open_on_start: bool = self.settings.value("open_on_start", True, type=bool)

        # Next scheduled *auto* refresh (UTC)
        self.next_refresh_deadline: Optional[datetime] = None

        # Track unseen changes for attention icon
        self.unseen_change: bool = False

        # Whether we've already shown the "still running in tray" hint
        self._hide_to_tray_hint_shown: bool = self.settings.value(
            "hide_to_tray_hint_shown", False, type=bool
        )

        # UI visibility prefs
        # show_tooltip: whether tray tooltip shows the detailed status block
        # show_menu_info: whether "Status…" submenu appears in tray menu
        self.show_tooltip: bool = self.settings.value("show_tooltip", True, type=bool)
        self.show_menu_info: bool = self.settings.value(
            "show_menu_info", True, type=bool
        )

        # Last time we actually hit the remote site (UTC), persisted in QSettings
        last_iso = self.settings.value("last_refresh_utc", "", type=str)
        if last_iso:
            try:
                lr = datetime.fromisoformat(last_iso)
                if lr.tzinfo is None:
                    lr = lr.replace(tzinfo=timezone.utc)
                self.last_refresh_utc: Optional[datetime] = lr
            except Exception:
                self.last_refresh_utc = None
        else:
            self.last_refresh_utc = None

        # Timers
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._on_refresh_timer)

        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_refresh_ui)

        # Tray icon and menu
        self.tray_icon = QSystemTrayIcon(self.window)
        self._setup_tray_icon()
        self._setup_menu()

        self.tray_icon.activated.connect(self.on_tray_activated)

        # Start timers according to current settings
        self.update_timer()

        # Finally show tray icon
        self.tray_icon.show()

    # ------------------------------------------------------------------ #
    # Initial load
    # ------------------------------------------------------------------ #

    def initial_load(self) -> None:
        """Perform the initial cache refresh and UI update.

        Respects offline-first rules and minimum scrape interval.
        """
        use_network = self._should_refresh_with_network()
        changed = self.window.refresh_codes(initial=True, use_network=use_network)
        if use_network:
            self._update_last_refresh()
        if changed:
            self._on_code_changed()
        self.update_refresh_ui()

    # ------------------------------------------------------------------ #
    # Tray icon, menu, and theme
    # ------------------------------------------------------------------ #

    def _setup_tray_icon(self) -> None:
        base_mono = load_tray_base_icon()
        self.tray_icon_dark = recolor_icon(base_mono, QColor(0, 0, 0))
        self.tray_icon_light = recolor_icon(base_mono, QColor(255, 255, 255))
        self.attention_tray_icon_dark = create_attention_icon(self.tray_icon_dark)
        self.attention_tray_icon_light = create_attention_icon(self.tray_icon_light)

        # Set app icon globally for consistency
        app_icon = load_app_icon()
        if not app_icon.isNull():
            QApplication.instance().setWindowIcon(app_icon)

        self.update_tray_icon()

    def _setup_menu(self) -> None:
        tray_menu = QMenu()

        # Title at top (disabled)
        self.action_title = QAction(APP_NAME, tray_menu)
        self.action_title.setEnabled(False)
        tray_menu.addAction(self.action_title)

        tray_menu.addSeparator()

        # Primary actions
        self.action_show = QAction("Open main window", tray_menu)
        self.action_show.triggered.connect(self.show_normal_from_tray)
        tray_menu.addAction(self.action_show)

        self.action_refresh = QAction("Refresh now", tray_menu)
        self.action_refresh.triggered.connect(self._refresh_now)
        tray_menu.addAction(self.action_refresh)

        tray_menu.addSeparator()

        # Status submenu (detailed info; mirrors tooltip content, but simpler)
        self.status_menu = tray_menu.addMenu("Status…")
        self.status_menu_action = self.status_menu.menuAction()

        self.status_title = QAction("Activation & time status", self.status_menu)
        self.status_title.setEnabled(False)
        self.status_menu.addAction(self.status_title)

        self.status_menu.addSeparator()

        self.status_schedule = QAction("", self.status_menu)
        self.status_menu.addAction(self.status_schedule)

        self.status_last = QAction("", self.status_menu)
        self.status_menu.addAction(self.status_last)

        self.status_next = QAction("", self.status_menu)
        self.status_menu.addAction(self.status_next)

        self.status_menu.addSeparator()

        self.status_zone = QAction("", self.status_menu)
        self.status_menu.addAction(self.status_zone)

        self.status_now = QAction("", self.status_menu)
        self.status_menu.addAction(self.status_now)

        self.status_next_run = QAction("", self.status_menu)
        self.status_menu.addAction(self.status_next_run)

        # Initial visibility based on preference
        self.status_menu_action.setVisible(self.show_menu_info)

        tray_menu.addSeparator()

        # Settings window
        self.action_settings = QAction("Settings…", tray_menu)
        self.action_settings.triggered.connect(self.open_settings)
        tray_menu.addAction(self.action_settings)

        tray_menu.addSeparator()

        # About and Quit
        self.action_about = QAction("About…", tray_menu)
        self.action_about.triggered.connect(lambda: show_about_dialog(self.window))
        tray_menu.addAction(self.action_about)

        tray_menu.addSeparator()

        self.action_quit = QAction("Quit", tray_menu)
        self.action_quit.triggered.connect(self.quit_from_tray)
        tray_menu.addAction(self.action_quit)

        self.tray_icon.setContextMenu(tray_menu)

    def open_settings(self) -> None:
        """Open the unified Settings dialog (lazy import to avoid cycles)."""
        from fc_token.ui.dialogs.settings import run_settings_dialog

        run_settings_dialog(self.window, self)

    def set_icon_mode(self, mode: str) -> None:
        """Set tray icon appearance mode ('auto', 'light', 'dark')."""
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

    # ------------------------------------------------------------------ #
    # User-visible notifications
    # ------------------------------------------------------------------ #

    def show_info_message(self, title: str, text: str, msec: int = 3000) -> None:
        """Show a transient informational tray notification."""
        self.tray_icon.showMessage(
            title,
            text,
            QSystemTrayIcon.MessageIcon.Information,
            msec,
        )

    def clear_attention_flag(self) -> None:
        """Clear the 'new code' attention dot on the tray icon."""
        self.unseen_change = False
        self.update_tray_icon()

    # ------------------------------------------------------------------ #
    # Tray interactions
    # ------------------------------------------------------------------ #

    def is_tray_visible(self) -> bool:
        return self.tray_icon.isVisible()

    def notify_hidden_to_tray(self) -> None:
        """Notify the user that the app is still running in the tray (once)."""
        if self._hide_to_tray_hint_shown:
            return

        self.tray_icon.showMessage(
            "File Centipede",
            "Still running in the system tray. Use the tray icon menu to quit.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        self._hide_to_tray_hint_shown = True
        self.settings.setValue("hide_to_tray_hint_shown", True)

    def show_normal_from_tray(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        # If user has seen the window, clear attention flag
        self.clear_attention_flag()

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Left-click toggles window visibility
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible():
                self.window.hide()
            else:
                self.show_normal_from_tray()

    def quit_from_tray(self) -> None:
        self.refresh_timer.stop()
        self.countdown_timer.stop()
        QApplication.instance().quit()

    # ------------------------------------------------------------------ #
    # Scheduling and refresh
    # ------------------------------------------------------------------ #

    def _format_interval_minutes(self, minutes: int) -> str:
        days = minutes // (24 * 60)
        hours = (minutes // 60) % 24
        mins = minutes % 60
        parts: list[str] = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if mins and not days and not hours:
            parts.append(f"{mins}m")
        if not parts:
            return "0m"
        return " ".join(parts)

    def _format_interval_seconds(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        minutes = max(1, seconds // 60)
        return self._format_interval_minutes(minutes)

    def _update_last_refresh(self) -> None:
        """Record the timestamp of the last successful online refresh."""
        now_utc = datetime.now(timezone.utc)
        self.last_refresh_utc = now_utc
        self.settings.setValue("last_refresh_utc", now_utc.isoformat())

    def get_next_allowed_refresh_info(
        self,
    ) -> tuple[Optional[datetime], Optional[int]]:
        """Return (next_allowed_utc, remaining_seconds) for an online refresh
        based on the 6-hour floor.

        If there is no restriction (never refreshed before or floor already passed),
        returns (None, None) or (None, 0).
        """
        if self.last_refresh_utc is None:
            return None, None

        now_utc = datetime.now(timezone.utc)
        base = self.last_refresh_utc
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)

        next_allowed = base + timedelta(minutes=MIN_REFRESH_MINUTES)
        remaining_sec = int((next_allowed - now_utc).total_seconds())
        if remaining_sec <= 0:
            return None, 0
        return next_allowed, remaining_sec

    def _should_refresh_with_network(self) -> bool:
        """Decide whether to hit the remote site or stay offline.

        Rules:
        - If the cache already contains *any* future codes (end >= now), stay offline.
        - Otherwise, enforce a hard 6-hour floor between online scrapes:
            elapsed_since_last_scrape >= MIN_REFRESH_MINUTES
          is REQUIRED before scraping again.
        - First run (no last_refresh_utc): allow exactly one initial scrape.
        """
        now_utc = datetime.now(timezone.utc)
        codes = self.cache.load()

        # First-ever run: no last_refresh_utc recorded → allow one scrape.
        if self.last_refresh_utc is None:
            return True

        # If we still have any future codes, stay offline.
        if any(c.end >= now_utc for c in codes):
            return False

        # No active future codes. Enforce the 6-hour floor.
        base = self.last_refresh_utc
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)

        elapsed_min = (now_utc - base).total_seconds() / 60.0
        if elapsed_min < MIN_REFRESH_MINUTES:
            return False

        # Floor passed, and no active codes → allowed.
        return True

    def update_timer(self) -> None:
        """Reconfigure timers based on current settings."""
        self.refresh_timer.stop()
        self.countdown_timer.stop()
        self.next_refresh_deadline = None

        if not self.auto_refresh_enabled:
            self.update_refresh_ui()
            return

        now_utc = datetime.now(timezone.utc)
        self.next_refresh_deadline = now_utc + timedelta(minutes=AUTO_REFRESH_MINUTES)

        # Auto refresh once per day (attempts; may stay offline if future codes exist)
        interval_ms = AUTO_REFRESH_MINUTES * 60 * 1000
        self.refresh_timer.start(interval_ms)
        # Update countdown every 60 seconds
        self.countdown_timer.start(60 * 1000)
        self.update_refresh_ui()

    def _on_refresh_timer(self) -> None:
        use_network = self._should_refresh_with_network()
        changed = self.window.refresh_codes(initial=False, use_network=use_network)
        if use_network:
            self._update_last_refresh()
        if changed:
            self._on_code_changed()

        if self.auto_refresh_enabled:
            now_utc = datetime.now(timezone.utc)
            self.next_refresh_deadline = now_utc + timedelta(
                minutes=AUTO_REFRESH_MINUTES
            )

        self.update_refresh_ui()

    def _show_refresh_delay_info(self) -> None:
        """Show an info box explaining when an online refresh is allowed (floor)."""
        from PyQt6.QtWidgets import QMessageBox as MB

        next_allowed_utc, remaining_sec = self.get_next_allowed_refresh_info()

        if not next_allowed_utc or remaining_sec is None or remaining_sec <= 0:
            message = (
                "Online refresh is temporarily unavailable.\n\n"
                "The helper will try again later when it is allowed to contact "
                "the File Centipede site."
            )
        else:
            local_zone = get_local_zone(DEFAULT_TIMEZONE)
            next_local = next_allowed_utc.astimezone(local_zone)
            next_time_str = next_local.strftime("%b %d, %Y %I:%M %p")
            human_remaining = self._format_interval_seconds(remaining_sec)
            message = (
                "Online refresh is not yet allowed.\n\n"
                f"The next online refresh can occur in about {human_remaining}, "
                f"around {next_time_str}.\n\n"
                "You can still use any activation codes that are already cached."
            )

        box = MB(self.window)
        box.setIcon(MB.Icon.Information)
        box.setWindowTitle("Online refresh delayed")
        box.setText(message)
        box.addButton("Understood", MB.ButtonRole.AcceptRole)
        box.exec()

    def _show_active_codes_block_info(self, last_end: datetime) -> None:
        """Explain that online refresh is skipped because future codes exist."""
        from PyQt6.QtWidgets import QMessageBox as MB

        local_zone = get_local_zone(DEFAULT_TIMEZONE)
        end_local = last_end.astimezone(local_zone)
        end_str = end_local.strftime("%b %d, %Y %I:%M %p")

        message = (
            "The helper already has activation codes cached into the future.\n\n"
            "To avoid unnecessary traffic, it will not contact the File Centipede "
            "site again until those cached codes have expired.\n\n"
            f"Your current codes are valid until approximately {end_str}.\n"
            "You can continue using the app normally until then."
        )

        box = MB(self.window)
        box.setIcon(MB.Icon.Information)
        box.setWindowTitle("Using cached activation codes")
        box.setText(message)
        box.addButton("Understood", MB.ButtonRole.AcceptRole)
        box.exec()

    def _refresh_now(self) -> None:
        """Manual refresh from tray.

        - If blocked by active future codes, explain that and show their expiry.
        - If blocked by the 6-hour floor, explain next allowed time.
        """
        now_utc = datetime.now(timezone.utc)
        codes = self.cache.load()
        active_codes = [c for c in codes if c.end >= now_utc]
        has_active = bool(active_codes)

        # Floor state (only relevant when there are no active codes)
        floor_block = False
        if self.last_refresh_utc is not None:
            base = self.last_refresh_utc
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            floor_block = (now_utc - base) < timedelta(minutes=MIN_REFRESH_MINUTES)

        use_network = self._should_refresh_with_network()

        if not use_network:
            if has_active:
                # Blocked because we already have future codes.
                last_end = max(c.end for c in active_codes)
                self._show_active_codes_block_info(last_end)
            elif floor_block:
                # No active codes, but blocked by the 6-hour floor.
                self._show_refresh_delay_info()
            else:
                # Fallback (should be rare)
                self._show_refresh_delay_info()

        changed = self.window.refresh_codes(initial=False, use_network=use_network)
        if use_network:
            self._update_last_refresh()
        if changed:
            self._on_code_changed()
        self.update_refresh_ui()

    def _on_code_changed(self) -> None:
        self.unseen_change = True
        self.update_tray_icon()
        self.tray_icon.showMessage(
            "Activation code updated",
            "A new File Centipede activation code is available.",
            QSystemTrayIcon.MessageIcon.Information,
            8000,
        )

    def update_refresh_ui(self) -> None:
        """Update tray tooltip and Status submenu."""
        now_utc = datetime.now(timezone.utc)

        # --- Last refresh age ---
        if self.last_refresh_utc is None:
            last_age_str = "never"
        else:
            base = self.last_refresh_utc
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            age_sec = max(0, int((now_utc - base).total_seconds()))
            last_age_str = f"{self._format_interval_seconds(age_sec)} ago"

        # --- Next auto refresh (relative) ---
        if self.next_refresh_deadline is not None and self.auto_refresh_enabled:
            remaining_sec = int((self.next_refresh_deadline - now_utc).total_seconds())
            if remaining_sec < 0:
                remaining_sec = 0
            next_human = self._format_interval_seconds(remaining_sec)
            next_short_relative = f"in {next_human}"
        else:
            next_short_relative = "n/a"

        # --- Timezone + current local time ---
        tz_name = get_local_zone_name(DEFAULT_TIMEZONE)
        local_zone = get_local_zone(DEFAULT_TIMEZONE)
        now_local = datetime.now(local_zone)
        now_local_str = now_local.strftime("%b %d, %Y %I:%M %p")

        # Absolute next-run time in local tz (for auto schedule)
        if self.next_refresh_deadline is not None and self.auto_refresh_enabled:
            next_local = self.next_refresh_deadline.astimezone(local_zone)
            next_run_str = next_local.strftime("%b %d, %Y %I:%M %p")
        else:
            next_run_str = "n/a"

        # --- Common label width for tooltip alignment ---
        labels = {
            "schedule": "Schedule",
            "last": "Last",
            "next": "Next",
            "zone": "Zone",
            "now": "Now",
            "next_run": "Next run",
        }
        label_width = max(len(v) for v in labels.values())

        # Schedule text: daily auto vs off
        schedule_value = (
            "Auto (daily)" if self.auto_refresh_enabled else "Off (manual only)"
        )

        # Tooltip-style lines (with indent + aligned labels)
        schedule_line = (
            f"  📅 {labels['schedule'].ljust(label_width)} : {schedule_value}"
        )
        last_line = f"  ⏲️ {labels['last'].ljust(label_width)} : {last_age_str}"
        next_line = f"  ⏭️ {labels['next'].ljust(label_width)} : {next_short_relative}"
        zone_line = f"  📍 {labels['zone'].ljust(label_width)} : {tz_name}"
        now_line = f"  🕒 {labels['now'].ljust(label_width)} : {now_local_str}"
        next_run_line = f"  🔄 {labels['next_run'].ljust(label_width)} : {next_run_str}"

        # Menu-style lines (no indent, simpler)
        schedule_menu = f"📅 Schedule: {schedule_value}"
        last_menu = f"⏲️ Last: {last_age_str}"
        next_menu = f"⏭️ Next: {next_short_relative}"
        zone_menu = f"📍 Zone: {tz_name}"
        now_menu = f"🕒 Now: {now_local_str}"
        next_run_menu = f"🔄 Next run: {next_run_str}"

        # --- Update Status submenu ---
        if self.show_menu_info:
            self.status_menu_action.setVisible(True)
            self.status_schedule.setText(schedule_menu)
            self.status_last.setText(last_menu)
            self.status_next.setText(next_menu)
            self.status_zone.setText(zone_menu)
            self.status_now.setText(now_menu)
            self.status_next_run.setText(next_run_menu)
        else:
            self.status_menu_action.setVisible(False)

        # --- Tooltip content (full aligned layout) ---
        tooltip_lines = [
            APP_NAME,
            "",
            "[ ⏱ Refresh ]",
            schedule_line,
            last_line,
            next_line,
            "",
            "[ 🌐 Time ]",
            zone_line,
            now_line,
            next_run_line,
        ]
        tooltip_text = "\n".join(tooltip_lines)

        if self.show_tooltip:
            self.tray_icon.setToolTip(tooltip_text)
        else:
            self.tray_icon.setToolTip("")

    # ------------------------------------------------------------------ #
    # Settings handlers (used by Settings dialog)
    # ------------------------------------------------------------------ #

    def toggle_show_tooltip(self, enabled: bool) -> None:
        self.show_tooltip = enabled
        self.settings.setValue("show_tooltip", enabled)
        self.update_refresh_ui()

    def toggle_show_menu_info(self, enabled: bool) -> None:
        self.show_menu_info = enabled
        self.settings.setValue("show_menu_info", enabled)
        self.update_refresh_ui()

    def toggle_auto_refresh(self, enabled: bool) -> None:
        self.auto_refresh_enabled = enabled
        self.settings.setValue(KEY_AUTO_REFRESH, enabled)
        self.update_timer()
        self.tray_icon.showMessage(
            "File Centipede",
            "Daily auto-refresh enabled."
            if enabled
            else "Daily auto-refresh disabled.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def toggle_open_on_start(self, enabled: bool) -> None:
        """Persist whether the main window should be shown when the app starts."""
        self.open_on_start = enabled
        self.settings.setValue("open_on_start", enabled)

    # ------------------------------------------------------------------ #
    # Autostart / integration helpers
    # ------------------------------------------------------------------ #

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

    def uninstall_integration(self) -> None:
        """Remove .desktop file and icons installed for the current user."""
        from PyQt6.QtWidgets import QMessageBox as MB

        reply = MB.question(
            self.window,
            "Remove integration",
            "Remove the .desktop launcher and icons installed for this user?",
            MB.StandardButton.Yes | MB.StandardButton.No,
        )
        if reply != MB.StandardButton.Yes:
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
            MB.information(
                self.window,
                "Removed",
                "Launcher and/or icons removed for this user.",
            )
        else:
            MB.information(
                self.window,
                "Nothing to remove",
                "No installed launcher or icons were found.",
            )

    def change_timezone(self) -> None:
        """Open timezone dialog and persist the selected timezone."""
        new_tz = run_timezone_dialog(self.window)
        if not new_tz:
            return

        # Save preference
        self.settings.setValue(KEY_TIMEZONE, new_tz)

        # Refresh view and timers to reflect new timezone
        changed = self.window.refresh_codes(initial=False)
        if changed:
            self._on_code_changed()

        self.update_refresh_ui()
