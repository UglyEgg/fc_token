from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSettings, QTimer, QThread
from PyQt6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)
from PyQt6.QtGui import QAction, QColor

from fc_token.cache import CodeCache
from fc_token.config import (
    APP_NAME,
    KEY_AUTO_REFRESH,
    KEY_ICON_MODE,
    KEY_TIMEZONE,
    SETTINGS_APP,
    SETTINGS_ORG,
    DEFAULT_TIMEZONE,
    DESKTOP_FILENAME,
)
from fc_token.desktop_entry import build_autostart_desktop, build_launcher_desktop
from fc_token.icons import (
    create_attention_icon,
    is_dark_theme,
    load_app_icon,
    load_tray_base_icon,
    recolor_icon,
)
from fc_token.ui.devtools import (
    DevTools,
    INSTALL_TIMESTAMP_KEY,
    TOTAL_FOREGROUND_SECONDS_KEY,
)

from fc_token.ui.dialogs.about import show_about_dialog
from fc_token.ui.dialogs.timezone import run_timezone_dialog
from fc_token.ui.dialogs.settings import run_settings_dialog
from fc_token.ui.utils import get_local_zone_name, get_local_zone
from fc_token.ui.workers import RefreshWorker
from fc_token.scraper import refresh_source_timezone

# Minimum allowed refresh interval (minutes) between *online* scrapes.
# Global anti-abuse floor: 6 hours.
MIN_REFRESH_MINUTES = 360

# Auto-refresh schedule: once per day (used for the timer / "Next" info").
AUTO_REFRESH_MINUTES = 24 * 60

# Resource filenames packaged under fc_token/resources
ICON_PNG_NAME = "fc_token.png"
ICON_SYMBOLIC_NAME = "fc_token_symbolic.svg"

# Developer menu "honest lock": only enabled if this resource hash matches.
DEV_UNLOCK_RESOURCE_NAME = "uglyegg.png"
DEV_UNLOCK_HASH = "327acaa5006c55b3c7a0100cf75df7d1a3232ecc08e1c9cbb63da3619543bc4f"


class TrayController:
    """System tray integration, scheduling, notifications, and dev tooling."""

    def __init__(self, window, cache: CodeCache) -> None:
        self.window = window
        self.cache = cache

        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        # Uptime / lifecycle tracking
        install_iso = self.settings.value(INSTALL_TIMESTAMP_KEY, "", type=str)
        if not install_iso:
            now_utc = datetime.now(timezone.utc)
            self.settings.setValue(INSTALL_TIMESTAMP_KEY, now_utc.isoformat())

        # Track this session's start (foreground uptime)
        self.session_started_utc: datetime = datetime.now(timezone.utc)

        # Developer menu lock: only enabled if resource hash matches.
        self.dev_mode_enabled: bool = self._detect_dev_mode()

        # Icon mode: "auto", "light", "dark"
        self.icon_mode: str = self.settings.value(KEY_ICON_MODE, "auto", type=str)

        # Auto-refresh enabled flag (daily when enabled)
        self.auto_refresh_enabled: bool = self.settings.value(
            KEY_AUTO_REFRESH, True, type=bool
        )

        # Whether to open the main window on start
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

        # Timezone cache (for frequent status updates)
        self._tz_name_cache: str = ""
        self._tzinfo_cache = timezone.utc
        self._refresh_timezone_cache()

        # Timers
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._on_refresh_timer)

        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_refresh_ui)

        # Tray icon and menu
        self.tray_icon = QSystemTrayIcon(self.window)

        # Dev tools helper (exists even if menu is locked; UI just hidden)
        self.dev_tools = DevTools(self)

        self._setup_tray_icon()
        self._setup_menu()

        self.tray_icon.activated.connect(self.on_tray_activated)

        # Background-refresh state
        self._refresh_thread: QThread | None = None
        self._refresh_worker: RefreshWorker | None = None
        self._refresh_in_progress: bool = False
        self._current_refresh_initial: bool = False
        self._current_refresh_use_network: bool = False

        # For duration measurement of network scrapes
        self._current_refresh_started_at_utc: datetime | None = None

        # Start timers according to current settings
        self.update_timer()

        # Finally show tray icon
        self.tray_icon.show()

    # ------------------------------------------------------------------ #
    # Developer mode "lock"
    # ------------------------------------------------------------------ #

    def _detect_dev_mode(self) -> bool:
        """Return True if the developer menu should be enabled."""
        try:
            pkg_root = files("fc_token.resources")
            candidate = pkg_root.joinpath(DEV_UNLOCK_RESOURCE_NAME)
            src_path = Path(str(candidate))
            if not src_path.is_file():
                return False
            data = src_path.read_bytes()
        except Exception:
            return False

        digest = hashlib.sha256(data).hexdigest()
        return digest == DEV_UNLOCK_HASH

    # ------------------------------------------------------------------ #
    # Initial load
    # ------------------------------------------------------------------ #

    def initial_load(self, *, use_network: bool | None = None) -> None:
        """Perform the initial cache refresh and UI update.

        Respects offline-first rules and minimum scrape interval.
        """
        if use_network is None:
            use_network = self._should_refresh_with_network()

        if use_network:
            self._start_refresh_task(initial=True, use_network=True)
        else:
            changed = self.window.refresh_from_cache(initial=True)
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

        # Developer submenu (only when dev_mode_enabled)
        if self.dev_mode_enabled:
            self.dev_menu = tray_menu.addMenu("Developer")
            self.dev_menu_action = self.dev_menu.menuAction()

            # Debug info / cache tools
            self.dev_show_info = QAction("Debug info…", self.dev_menu)
            self.dev_show_info.triggered.connect(self.dev_tools.show_debug_info)
            self.dev_menu.addAction(self.dev_show_info)

            self.dev_open_cache = QAction("Open cache folder", self.dev_menu)
            self.dev_open_cache.triggered.connect(self.dev_tools.open_cache_folder)
            self.dev_menu.addAction(self.dev_open_cache)

            self.dev_menu.addSeparator()

            self.dev_view_cache_json = QAction("Cache JSON…", self.dev_menu)
            self.dev_view_cache_json.triggered.connect(self.dev_tools.show_cache_json)
            self.dev_menu.addAction(self.dev_view_cache_json)

            self.dev_menu.addSeparator()

            # Time simulation and timeline
            self.dev_simulate_time = QAction("Simulate time…", self.dev_menu)
            self.dev_simulate_time.triggered.connect(
                self.dev_tools.simulate_time_dialog
            )
            self.dev_menu.addAction(self.dev_simulate_time)

            self.dev_show_timeline = QAction("Show code timeline…", self.dev_menu)
            self.dev_show_timeline.triggered.connect(self.dev_tools.show_code_timeline)
            self.dev_menu.addAction(self.dev_show_timeline)

            self.dev_menu.addSeparator()

            # Force refresh & stats
            self.dev_force_refresh = QAction(
                "Force online refresh (ignore limits)", self.dev_menu
            )
            self.dev_force_refresh.triggered.connect(self._force_online_refresh)
            self.dev_menu.addAction(self.dev_force_refresh)

            self.dev_menu.addSeparator()

            self.dev_view_stats = QAction("Scrape stats…", self.dev_menu)
            self.dev_view_stats.triggered.connect(self.dev_tools.show_scrape_stats)
            self.dev_menu.addAction(self.dev_view_stats)

            # Purge cache & settings reset
            self.dev_menu.addSeparator()

            self.dev_purge_cache = QAction("Purge cache and re-sync…", self.dev_menu)
            self.dev_purge_cache.triggered.connect(
                self.dev_tools.purge_cache_and_resync
            )
            self.dev_menu.addAction(self.dev_purge_cache)

            self.dev_reset_settings = QAction(
                "Reset settings to defaults…", self.dev_menu
            )
            self.dev_reset_settings.triggered.connect(
                self.dev_tools.reset_settings_to_defaults
            )
            self.dev_menu.addAction(self.dev_reset_settings)

            tray_menu.addSeparator()

        # Settings window
        self.action_settings = QAction("Settings…", tray_menu)
        self.action_settings.triggered.connect(self.open_settings)
        tray_menu.addAction(self.action_settings)

        tray_menu.addSeparator()

        # About and Quit
        self.action_about = QAction("About…", tray_menu)
        # Pass self so About dialog / big egg can use dev_tools for stats
        self.action_about.triggered.connect(
            lambda: show_about_dialog(self.window, self)
        )
        tray_menu.addAction(self.action_about)

        tray_menu.addSeparator()

        self.action_quit = QAction("Quit", tray_menu)
        self.action_quit.triggered.connect(self.quit_from_tray)
        tray_menu.addAction(self.action_quit)

        self.tray_icon.setContextMenu(tray_menu)

    def open_settings(self) -> None:
        """Open the unified Settings dialog."""
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
    # User-visible notifications & tray interactions
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
        # Stop periodic timers
        self.refresh_timer.stop()
        self.countdown_timer.stop()

        # Ensure any background refresh completes cleanly
        self._cancel_refresh_thread()

        # Accumulate foreground uptime into TOTAL_FOREGROUND_SECONDS_KEY
        try:
            total_foreground = int(
                self.settings.value(TOTAL_FOREGROUND_SECONDS_KEY, 0, type=int)
            )
        except Exception:
            total_foreground = 0

        now_utc = datetime.now(timezone.utc)
        elapsed = now_utc - self.session_started_utc
        extra_seconds = max(0, int(elapsed.total_seconds()))
        self.settings.setValue(
            TOTAL_FOREGROUND_SECONDS_KEY,
            total_foreground + extra_seconds,
        )

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
        """Return (next_allowed_utc, remaining_seconds) for an online refresh."""
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
        """Decide whether to hit the remote site or stay offline."""
        now_utc = datetime.now(timezone.utc)
        codes = self.cache.get_codes()

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
        if use_network:
            self._start_refresh_task(initial=False, use_network=True)
        else:
            changed = self.window.refresh_from_cache(initial=False)
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
        next_allowed_utc, remaining_sec = self.get_next_allowed_refresh_info()

        if not next_allowed_utc or remaining_sec is None or remaining_sec <= 0:
            message = (
                "Online refresh is temporarily unavailable.\n\n"
                "The helper will try again later when it is allowed to contact "
                "the File Centipede site."
            )
        else:
            local_zone = self._get_local_zone()
            next_local = next_allowed_utc.astimezone(local_zone)
            next_time_str = next_local.strftime("%b %d, %Y %I:%M %p")
            human_remaining = self._format_interval_seconds(remaining_sec)
            message = (
                "Online refresh is not yet allowed.\n\n"
                f"The next online refresh can occur in about {human_remaining}, "
                f"around {next_time_str}.\n\n"
                "You can still use any activation codes that are already cached."
            )

        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Online refresh delayed")
        box.setText(message)
        box.addButton("Understood", QMessageBox.ButtonRole.AcceptRole)
        box.exec()

    def _show_active_codes_block_info(self, last_end: datetime) -> None:
        """Explain that online refresh is skipped because future codes exist."""
        local_zone = self._get_local_zone()
        end_local = last_end.astimezone(local_zone)
        end_str = end_local.strftime("%b %d, %Y %I:%M %p")

        message = (
            "The helper already has activation codes cached into the future.\n\n"
            "To avoid unnecessary traffic, it will not contact the File Centipede "
            "site again until those cached codes have expired.\n\n"
            f"Your current codes are valid until approximately {end_str}.\n\n"
            "You can continue using the app normally until then."
        )

        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Using cached activation codes")
        box.setText(message)
        box.addButton("Understood", QMessageBox.ButtonRole.AcceptRole)
        box.exec()

    def _refresh_now(self) -> None:
        """Manual refresh from tray, respecting normal rules."""
        now_utc = datetime.now(timezone.utc)
        codes = self.cache.get_codes()
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

            # Even when network refresh is blocked, update UI from cache.
            changed = self.window.refresh_from_cache(initial=False)
            if changed:
                self._on_code_changed()
            self.update_refresh_ui()
            return

        # Network refresh is allowed → run via background worker.
        self._start_refresh_task(initial=False, use_network=True)

    def _force_online_refresh(self) -> None:
        """Developer: force an online refresh ignoring cache/floor rules."""
        if self._refresh_in_progress:
            QMessageBox.information(
                self.window,
                "Developer",
                "A refresh is already in progress.",
            )
            return

        reply = QMessageBox.question(
            self.window,
            "Force online refresh",
            "Force an online refresh now, ignoring normal limits?\n\n"
            "This will contact the File Centipede site immediately, even if:\n"
            "  • Cached activation codes are still valid, or\n"
            "  • The minimum interval between scrapes has not elapsed.\n\n"
            "Use this sparingly.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_refresh_task(initial=False, use_network=True)

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

        # Fetch codes once so we can reason about future coverage.
        codes = self.cache.get_codes()
        active_codes = [c for c in codes if c.end >= now_utc]
        has_active_codes = bool(active_codes)

        # --- Last refresh age ---
        if self.last_refresh_utc is None:
            last_age_str = "never"
        else:
            base = self.last_refresh_utc
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            age_sec = max(0, int((now_utc - base).total_seconds()))
            last_age_str = f"{self._format_interval_seconds(age_sec)} ago"

        # --- Timezone + current local time ---
        tz_name = self._get_local_zone_name()
        local_zone = self._get_local_zone()
        now_local = datetime.now(local_zone)
        now_local_str = now_local.strftime("%b %d, %Y %I:%M %p")

        # --- Next auto / online refresh info ---
        if has_active_codes:
            # We have codes that are valid into the future; no online refresh
            # will occur until the last of them expires.
            last_end_utc = max(c.end for c in active_codes)
            if last_end_utc.tzinfo is None:
                last_end_utc = last_end_utc.replace(tzinfo=timezone.utc)

            remaining_sec_codes = int((last_end_utc - now_utc).total_seconds())
            if remaining_sec_codes < 0:
                remaining_sec_codes = 0

            # "Next" becomes "how long codes are still valid".
            next_short_relative = (
                "cached codes valid for "
                f"{self._format_interval_seconds(remaining_sec_codes)}"
            )

            # "Next run" shows when those codes expire locally.
            last_end_local = last_end_utc.astimezone(local_zone)
            next_run_str = last_end_local.strftime("%b %d, %Y %I:%M %p")
        else:
            # No future codes cached; fall back to daily auto-refresh schedule.
            if self.next_refresh_deadline is not None and self.auto_refresh_enabled:
                remaining_sec = int(
                    (self.next_refresh_deadline - now_utc).total_seconds()
                )
                if remaining_sec < 0:
                    remaining_sec = 0
                next_human = self._format_interval_seconds(remaining_sec)
                next_short_relative = f"in {next_human}"

                next_local = self.next_refresh_deadline.astimezone(local_zone)
                next_run_str = next_local.strftime("%b %d, %Y %I:%M %p")
            else:
                next_short_relative = "n/a"
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
    # Settings handlers
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
        """Persist the "open main window on start" preference."""
        self.open_on_start = enabled
        self.settings.setValue("open_on_start", enabled)

    # ------------------------------------------------------------------ #
    # Autostart helpers
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
            desktop_content = build_autostart_desktop()
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

    # ------------------------------------------------------------------ #
    # Desktop launcher / icon integration
    # ------------------------------------------------------------------ #

    def _user_prefix(self) -> Path:
        """Return the base prefix for this user's XDG data directory."""
        data_home = os.environ.get(
            "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
        )
        return Path(data_home)

    def _desktop_paths(self) -> tuple[Path, Path, Path]:
        """Return (desktop_target, png_target, symbolic_target) for user scope."""
        prefix = self._user_prefix()
        applications_dir = prefix / "applications"
        icons_dir = prefix / "icons" / "hicolor"

        desktop_target = applications_dir / DESKTOP_FILENAME
        png_target = icons_dir / "256x256" / "apps" / ICON_PNG_NAME
        symbolic_target = icons_dir / "scalable" / "apps" / "fc_token-symbolic.svg"

        return desktop_target, png_target, symbolic_target

    def is_desktop_integrated(self) -> bool:
        """Return True if a user-level launcher/icons are present."""
        desktop_target, png_target, symbolic_target = self._desktop_paths()
        return any(p.exists() for p in (desktop_target, png_target, symbolic_target))

    def _write_text_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _copy_resource_if_available(self, name: str, dst: Path) -> None:
        try:
            pkg_root = files("fc_token.resources")
            candidate = pkg_root.joinpath(name)
            src_path = Path(str(candidate))
            if src_path.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src_path.read_bytes())
        except Exception:
            # Best-effort; ignore resource copy failures.
            pass

    def set_desktop_integration_enabled(self, enabled: bool) -> None:
        """Install or remove the user-level launcher/icons based on `enabled`."""
        desktop_target, png_target, symbolic_target = self._desktop_paths()

        if enabled:
            try:
                # Write .desktop file
                content = build_launcher_desktop()
                self._write_text_file(desktop_target, content)

                # Copy icons from packaged resources if available
                self._copy_resource_if_available(ICON_PNG_NAME, png_target)
                self._copy_resource_if_available(ICON_SYMBOLIC_NAME, symbolic_target)

                QMessageBox.information(
                    self.window,
                    "Desktop integration",
                    "Launcher and icons have been installed (or were already present).",
                )
            except Exception as exc:
                QMessageBox.warning(
                    self.window,
                    "Desktop integration",
                    f"Could not install launcher/icons:\n{exc}",
                )
        else:
            # Remove .desktop and icons if present
            removed_any = False
            for path in (desktop_target, png_target, symbolic_target):
                try:
                    if path.exists():
                        path.unlink()
                        removed_any = True
                except Exception:
                    # Ignore individual delete errors
                    pass

            if removed_any:
                QMessageBox.information(
                    self.window,
                    "Desktop integration",
                    "Launcher and icons have been removed.",
                )
            else:
                QMessageBox.information(
                    self.window,
                    "Desktop integration",
                    "No launcher or icons were found to remove.",
                )

    # ------------------------------------------------------------------ #
    # Timezone helpers
    # ------------------------------------------------------------------ #

    def change_timezone(self) -> None:
        """Open timezone dialog and persist the selected timezone."""
        new_tz = run_timezone_dialog(self.window)
        if not new_tz:
            return

        # Save preference
        self.settings.setValue(KEY_TIMEZONE, new_tz)

        # Refresh cached tzinfo & UI
        self._refresh_timezone_cache()
        refresh_source_timezone()

        # Refresh view from cache; no network access needed for tz-only change.
        changed = self.window.refresh_from_cache(initial=False)
        if changed:
            self._on_code_changed()

        self.update_refresh_ui()

    def _refresh_timezone_cache(self) -> None:
        self._tz_name_cache = get_local_zone_name(DEFAULT_TIMEZONE)
        self._tzinfo_cache = get_local_zone(DEFAULT_TIMEZONE)

    def _get_local_zone_name(self) -> str:
        return self._tz_name_cache

    def _get_local_zone(self):
        return self._tzinfo_cache

    # ------------------------------------------------------------------ #
    # Background refresh helpers
    # ------------------------------------------------------------------ #

    def _start_refresh_task(self, *, initial: bool, use_network: bool) -> None:
        """Start a background refresh if one is not already running."""
        if self._refresh_in_progress:
            return

        self._refresh_in_progress = True
        self._current_refresh_initial = initial
        self._current_refresh_use_network = use_network
        # Record start time for network scrapes (for duration stats / egg)
        if use_network:
            self._current_refresh_started_at_utc = datetime.now(timezone.utc)
        else:
            self._current_refresh_started_at_utc = None

        self.action_refresh.setEnabled(False)

        thread = QThread(self.window)
        worker = RefreshWorker(self.cache, self.window.url, use_network=use_network)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_refresh_success)
        worker.error.connect(self._on_refresh_error)
        worker.finished.connect(self._cleanup_refresh_thread)
        worker.error.connect(self._cleanup_refresh_thread)

        self._refresh_thread = thread
        self._refresh_worker = worker

        thread.start()

    def _on_refresh_success(self, codes: list) -> None:
        """Handle successful completion of a background refresh."""
        changed = self.window.refresh_from_codes(
            codes,
            initial=self._current_refresh_initial,
        )

        duration_sec: float | None = None
        if self._current_refresh_use_network and self._current_refresh_started_at_utc:
            now_utc = datetime.now(timezone.utc)
            delta = now_utc - self._current_refresh_started_at_utc
            duration_sec = max(0.0, delta.total_seconds())

        if self._current_refresh_use_network:
            self._update_last_refresh()
            # Record scrape stats (for dev menu + egg compact stats)
            # Always record for all users; DevTools handles nag dev-mode guard.
            try:
                self.dev_tools.record_scrape_stats(codes, duration_seconds=duration_sec)
            except TypeError:
                # Backwards compatibility in case dev_tools has old signature
                self.dev_tools.record_scrape_stats(codes)  # type: ignore[arg-type]

        if self.auto_refresh_enabled:
            now_utc = datetime.now(timezone.utc)
            self.next_refresh_deadline = now_utc + timedelta(
                minutes=AUTO_REFRESH_MINUTES
            )

        if changed:
            self._on_code_changed()

        self.update_refresh_ui()

    def _on_refresh_error(self, message: str) -> None:
        """Handle a refresh failure (network or parsing)."""
        # Keep using whatever is already cached; just refresh UI from cache.
        self.window.refresh_from_cache(initial=self._current_refresh_initial)
        self.update_refresh_ui()

        self.tray_icon.showMessage(
            "Refresh failed",
            f"Could not refresh activation codes:\n{message}",
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )

    def _cleanup_refresh_thread(self) -> None:
        self._refresh_in_progress = False
        self._current_refresh_started_at_utc = None
        self.action_refresh.setEnabled(True)

        if self._refresh_worker is not None:
            self._refresh_worker.deleteLater()
            self._refresh_worker = None

        if self._refresh_thread is not None:
            self._refresh_thread.quit()
            self._refresh_thread.wait()
            self._refresh_thread.deleteLater()
            self._refresh_thread = None

    def _cancel_refresh_thread(self) -> None:
        if not self._refresh_in_progress:
            return
        if self._refresh_thread is not None:
            self._refresh_thread.quit()
            self._refresh_thread.wait()
            self._refresh_thread.deleteLater()
            self._refresh_thread = None

        if self._refresh_worker is not None:
            self._refresh_worker.deleteLater()
            self._refresh_worker = None

        self._refresh_in_progress = False
        self._current_refresh_started_at_utc = None
        self.action_refresh.setEnabled(True)
