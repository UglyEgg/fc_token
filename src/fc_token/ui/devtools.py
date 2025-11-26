from __future__ import annotations

"""Developer tools and diagnostics for fc-token.

This module is only used behind the "Developer" menu. It exposes a
:class:`DevTools` helper that the :class:`TrayController` wires actions to.

The goals are:
- Provide rich debug information about cache, timezones and scheduling.
- Expose "stats for geeks" about online scrapes.
- Offer safe operations such as purging the cache or resetting settings.
- Implement the user-facing File Centipede "please register" nag logic.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from fc_token.config import APP_NAME, APP_VERSION

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from fc_token.ui.tray import TrayController


# Scrape stats settings key (stored in QSettings)
SCRAPE_STATS_KEY = "stats/scrape_log"
SCRAPE_STATS_MAX_ENTRIES = 200

# Nag-screen configuration
REGISTER_NAG_THRESHOLD = 20  # activation codes per nag cycle
REGISTER_NAG_PROGRESS_KEY = "nag/accumulated_codes"
REGISTER_URL = "https://filecxx.com/en_US/activation_code.html"


@dataclass
class DevTools:
    """Developer-only tools and views.

    Instances of this class are created and owned by :class:`TrayController`.
    """

    controller: "TrayController"

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    @property
    def c(self) -> "TrayController":  # convenience alias
        return self.controller

    def _format_bytes(self, value: int) -> str:
        units = ["B", "KiB", "MiB", "GiB"]
        v = float(value)
        for u in units:
            if v < 1024.0 or u == units[-1]:
                return f"{v:.1f} {u}" if u != "B" else f"{int(v)} B"
            v /= 1024.0
        return f"{value} B"

    # ------------------------------------------------------------------
    # Debug report
    # ------------------------------------------------------------------

    def _build_debug_report(self) -> str:
        """Build a multi-line debug snapshot for Developer → Debug info."""
        c = self.c

        app_name = APP_NAME
        app_version = APP_VERSION

        # Timezones
        local_tz_name = c._get_local_zone_name()
        local_zone = c._get_local_zone()
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(local_zone)

        # Source/site timezone from config if available
        try:
            from fc_token import config as config_module  # type: ignore

            source_tz = getattr(config_module, "FILE_CENTIPEDE_TIMEZONE", "UTC")
        except Exception:  # pragma: no cover - defensive
            source_tz = "unknown"

        # Refresh / schedule info
        last_refresh = getattr(c, "last_refresh_utc", None)
        if last_refresh is None:
            last_refresh_utc_str = "never"
            last_refresh_local_str = "never"
        else:
            lr_utc = last_refresh
            if lr_utc.tzinfo is None:
                lr_utc = lr_utc.replace(tzinfo=timezone.utc)
            last_refresh_utc_str = lr_utc.isoformat()
            last_refresh_local_str = lr_utc.astimezone(local_zone).isoformat()

        next_allowed_utc, remaining_sec = c.get_next_allowed_refresh_info()
        if next_allowed_utc is None:
            next_allowed_utc_str = "n/a"
            next_allowed_local_str = "n/a"
            remaining_str = "n/a"
        else:
            na_utc = next_allowed_utc
            if na_utc.tzinfo is None:
                na_utc = na_utc.replace(tzinfo=timezone.utc)
            next_allowed_utc_str = na_utc.isoformat()
            next_allowed_local_str = na_utc.astimezone(local_zone).isoformat()
            remaining_str = c._format_interval_seconds(max(0, remaining_sec or 0))

        if getattr(c, "next_refresh_deadline", None) is not None and c.auto_refresh_enabled:
            nd_utc = c.next_refresh_deadline
            if nd_utc.tzinfo is None:
                nd_utc = nd_utc.replace(tzinfo=timezone.utc)
            next_auto_utc_str = nd_utc.isoformat()
            next_auto_local_str = nd_utc.astimezone(local_zone).isoformat()
        else:
            next_auto_utc_str = "n/a"
            next_auto_local_str = "n/a"

        # Cache info
        codes = c.cache.get_codes()
        cache_dir = getattr(c.cache, "cache_dir", None)
        cache_path = getattr(c.cache, "cache_path", None)

        total_codes = len(codes)
        if codes:
            earliest = min(code.start for code in codes)
            latest = max(code.end for code in codes)
            earliest_utc = earliest.astimezone(timezone.utc)
            latest_utc = latest.astimezone(timezone.utc)
            earliest_local = earliest_utc.astimezone(local_zone)
            latest_local = latest_utc.astimezone(local_zone)
        else:
            earliest_utc = earliest_local = None
            latest_utc = latest_local = None

        # Active code at "now"
        active_entry = None
        for code in codes:
            try:
                if code.contains(now_utc):
                    active_entry = code
                    break
            except Exception:
                continue

        lines: list[str] = []
        lines.append("== File Centipede helper – Developer debug ==")
        lines.append("")
        lines.append("[App]")
        lines.append(f"  Name           : {app_name}")
        lines.append(f"  Version        : {app_version}")
        lines.append("")
        lines.append("[Timezones]")
        lines.append(f"  Source (site)  : {source_tz}")
        lines.append(f"  Display (user) : {local_tz_name}")
        lines.append(f"  Now (UTC)      : {now_utc.isoformat()}")
        lines.append(f"  Now (local)    : {now_local.isoformat()}")
        lines.append("")
        lines.append("[Refresh]")
        lines.append(f"  Auto refresh   : {c.auto_refresh_enabled}")
        lines.append(f"  Last online    : {last_refresh_utc_str}")
        lines.append(f"  Last online ⌁ : {last_refresh_local_str}")
        lines.append(f"  Next allowed   : {next_allowed_utc_str}")
        lines.append(f"  Next allowed ⌁ : {next_allowed_local_str}")
        lines.append(f"  Remaining floor: {remaining_str}")
        lines.append(f"  Next auto try  : {next_auto_utc_str}")
        lines.append(f"  Next auto try ⌁: {next_auto_local_str}")
        lines.append("")
        lines.append("[Cache]")
        lines.append(f"  Cache dir      : {cache_dir or 'unknown'}")
        lines.append(f"  Cache file     : {cache_path or 'unknown'}")
        lines.append(f"  Total codes    : {total_codes}")

        if earliest_utc is not None and latest_utc is not None:
            lines.append(f"  Earliest start : {earliest_utc.isoformat()}  (UTC)")
            lines.append(f"                    {earliest_local.isoformat()}  (local)")
            lines.append(f"  Latest end     : {latest_utc.isoformat()}  (UTC)")
            lines.append(f"                    {latest_local.isoformat()}  (local)")
        else:
            lines.append("  Earliest start : n/a")
            lines.append("  Latest end     : n/a")

        lines.append("")
        lines.append("[Active code @ now]")
        if active_entry is None:
            lines.append("  Active         : none")
        else:
            lines.append(f"  Code           : {getattr(active_entry, 'code', '<?>')}")
            try:
                start_utc = active_entry.start.astimezone(timezone.utc)
                end_utc = active_entry.end.astimezone(timezone.utc)
                start_local = active_entry.start.astimezone(local_zone)
                end_local = active_entry.end.astimezone(local_zone)
                lines.append(f"  Start (UTC)    : {start_utc.isoformat()}")
                lines.append(f"  End   (UTC)    : {end_utc.isoformat()}")
                lines.append(f"  Start (local)  : {start_local.isoformat()}")
                lines.append(f"  End   (local)  : {end_local.isoformat()}")
            except Exception:
                lines.append("  (could not render active entry timestamps)")

        return "\n".join(lines)

    def show_debug_info(self) -> None:
        report = self._build_debug_report()

        dlg = QDialog(self.c.window)
        dlg.setWindowTitle("Developer – Debug info")

        layout = QVBoxLayout(dlg)
        editor = QTextEdit(dlg)
        editor.setReadOnly(True)
        editor.setPlainText(report)
        layout.addWidget(editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
            | QDialogButtonBox.StandardButton.Reset,
            parent=dlg,
        )
        buttons.button(QDialogButtonBox.StandardButton.Reset).setText("Copy")
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)

        def do_copy() -> None:
            QApplication.clipboard().setText(report)

        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(do_copy)
        layout.addWidget(buttons)

        dlg.resize(700, 500)
        dlg.exec()

    # ------------------------------------------------------------------
    # Cache JSON
    # ------------------------------------------------------------------

    def _build_cache_json(self) -> str:
        codes = self.c.cache.get_codes()
        data = []
        for code in codes:
            try:
                data.append(code.to_dict())
            except Exception:
                data.append(
                    {
                        "code": getattr(code, "code", None),
                        "start": getattr(code, "start_str", None),
                        "end": getattr(code, "end_str", None),
                    }
                )
        import json

        return json.dumps(data, indent=2, sort_keys=True)

    def show_cache_json(self) -> None:
        text = self._build_cache_json()

        dlg = QDialog(self.c.window)
        dlg.setWindowTitle("Developer – Cache JSON")

        layout = QVBoxLayout(dlg)
        editor = QTextEdit(dlg)
        editor.setReadOnly(True)
        editor.setPlainText(text)
        layout.addWidget(editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
            | QDialogButtonBox.StandardButton.Reset,
            parent=dlg,
        )
        buttons.button(QDialogButtonBox.StandardButton.Reset).setText("Copy")
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)

        def do_copy() -> None:
            QApplication.clipboard().setText(text)

        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(do_copy)
        layout.addWidget(buttons)

        dlg.resize(700, 500)
        dlg.exec()

    def open_cache_folder(self) -> None:
        cache_dir = getattr(self.c.cache, "cache_dir", None)
        if not cache_dir:
            QMessageBox.warning(
                self.c.window,
                "Developer",
                "Cache directory is unknown.",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(cache_dir)))

    # ------------------------------------------------------------------
    # Time simulation & timeline
    # ------------------------------------------------------------------

    def _find_code_for_datetime(self, when_utc: datetime, codes: list) -> Optional[object]:
        if when_utc.tzinfo is None:
            when_utc = when_utc.replace(tzinfo=timezone.utc)
        else:
            when_utc = when_utc.astimezone(timezone.utc)
        for code in codes:
            try:
                if code.contains(when_utc):
                    return code
            except Exception:
                continue
        return None

    def simulate_time_dialog(self) -> None:
        local_zone = self.c._get_local_zone()
        now_local = datetime.now(local_zone)

        dlg = QDialog(self.c.window)
        dlg.setWindowTitle("Developer – Simulate time")

        layout = QVBoxLayout(dlg)

        row = QHBoxLayout()
        label = QLabel("Choose local date && time:")
        row.addWidget(label)

        dt_edit = QDateTimeEdit(dlg)
        dt_edit.setCalendarPopup(True)
        dt_edit.setDateTime(dt_edit.dateTime().fromString(
            now_local.strftime("%Y-%m-%d %H:%M:%S"), "yyyy-MM-dd HH:mm:ss"
        ))
        row.addWidget(dt_edit)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dlg,
        )
        layout.addWidget(buttons)

        def on_accept() -> None:
            qdt2 = dt_edit.dateTime()
            py_dt = qdt2.toPyDateTime()
            target_local = py_dt.replace(tzinfo=local_zone)
            target_utc = target_local.astimezone(timezone.utc)

            codes = self.c.cache.get_codes()
            active = self._find_code_for_datetime(target_utc, codes)

            if active is None:
                msg = (
                    "No cached activation code covers this time.\n\n"
                    f"Local: {target_local.isoformat()}\n"
                    f"UTC  : {target_utc.isoformat()}"
                )
            else:
                msg = (
                    "An activation code is active at this time.\n\n"
                    f"Code : {getattr(active, 'code', '<?>')}\n\n"
                    f"Start (UTC)   : {active.start.astimezone(timezone.utc).isoformat()}\n"
                    f"End   (UTC)   : {active.end.astimezone(timezone.utc).isoformat()}\n"
                    f"Start (local) : {active.start.astimezone(local_zone).isoformat()}\n"
                    f"End   (local) : {active.end.astimezone(local_zone).isoformat()}\n\n"
                    f"Target (local): {target_local.isoformat()}\n"
                    f"Target (UTC)  : {target_utc.isoformat()}"
                )

            QMessageBox.information(
                self.c.window,
                "Developer – Simulated result",
                msg,
            )

        buttons.accepted.connect(on_accept)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        dlg.resize(500, 150)
        dlg.exec()

    def show_code_timeline(self) -> None:
        local_zone = self.c._get_local_zone()
        now_utc = datetime.now(timezone.utc)

        codes = sorted(self.c.cache.get_codes(), key=lambda code: code.start)

        lines: list[str] = []
        lines.append("== File Centipede helper – Code timeline ==")
        lines.append("")
        lines.append(f"Now (UTC)  : {now_utc.isoformat()}")
        lines.append(f"Now (local): {now_utc.astimezone(local_zone).isoformat()}")
        lines.append("")

        if not codes:
            lines.append("No cached activation codes.")
        else:
            for idx, code in enumerate(codes, start=1):
                start_utc = code.start.astimezone(timezone.utc)
                end_utc = code.end.astimezone(timezone.utc)
                start_local = code.start.astimezone(local_zone)
                end_local = code.end.astimezone(local_zone)

                if end_utc < now_utc:
                    status = "[PAST]"
                elif code.contains(now_utc):
                    status = "[ACTIVE NOW]"
                else:
                    status = "[FUTURE]"

                lines.append(
                    f"{idx:02d}. {status} "
                    f"code={getattr(code, 'code', '<?>')}"
                )
                lines.append(f"        start (UTC)  : {start_utc.isoformat()}")
                lines.append(f"        end   (UTC)  : {end_utc.isoformat()}")
                lines.append(f"        start (local): {start_local.isoformat()}")
                lines.append(f"        end   (local): {end_local.isoformat()}")
                lines.append("")

        text = "\n".join(lines)

        dlg = QDialog(self.c.window)
        dlg.setWindowTitle("Developer – Code timeline")

        layout = QVBoxLayout(dlg)
        editor = QTextEdit(dlg)
        editor.setReadOnly(True)
        editor.setPlainText(text)
        layout.addWidget(editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            parent=dlg,
        )
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)

        dlg.resize(700, 500)
        dlg.exec()

    # ------------------------------------------------------------------
    # Scrape stats + nag support
    # ------------------------------------------------------------------

    def _load_scrape_stats(self) -> list[dict]:
        raw = self.c.settings.value(SCRAPE_STATS_KEY, "", type=str)
        if not raw:
            return []
        import json

        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    def _save_scrape_stats(self, stats: list[dict]) -> None:
        import json

        try:
            text = json.dumps(stats, ensure_ascii=False)
            self.c.settings.setValue(SCRAPE_STATS_KEY, text)
        except Exception:
            pass

    def record_scrape_stats(self, codes: list) -> None:
        """Record a single online scrape event for stats and nag logic.

        Called from TrayController._on_refresh_success when use_network=True.
        Uses metadata exposed on CodeCache (identity, body size, codes count).
        """
        now_utc = datetime.now(timezone.utc)
        local_zone = self.c._get_local_zone()
        now_local = now_utc.astimezone(local_zone)

        cache = self.c.cache
        identity = getattr(cache, "last_identity_used", None) or "unknown"
        raw_bytes = getattr(cache, "last_scrape_raw_bytes", None)
        codes_count = getattr(cache, "last_scraped_codes_count", None)

        # Fallbacks if metadata is missing
        import json

        if raw_bytes is None or raw_bytes <= 0:
            try:
                payload = [code.to_dict() for code in codes]
            except Exception:
                payload = [
                    {
                        "code": getattr(code, "code", None),
                        "start": getattr(code, "start_str", None),
                        "end": getattr(code, "end_str", None),
                    }
                    for code in codes
                ]
            raw_bytes = len(json.dumps(payload).encode("utf-8"))

        if codes_count is None or codes_count < 0:
            codes_count = len(codes)

        stats = self._load_scrape_stats()
        stats.append(
            {
                "at_utc": now_utc.isoformat(),
                "at_local": now_local.isoformat(),
                "bytes": int(raw_bytes),
                "codes": int(codes_count),
                "identity": identity,
            }
        )

        if len(stats) > SCRAPE_STATS_MAX_ENTRIES:
            stats = stats[-SCRAPE_STATS_MAX_ENTRIES:]

        self._save_scrape_stats(stats)

        # Update nag logic based on number of activation codes scraped
        self._update_nag_progress(codes_count=int(codes_count))

    def _build_scrape_stats_text(self) -> str:
        stats = self._load_scrape_stats()
        count = len(stats)

        total_bytes = sum(int(s.get("bytes", 0)) for s in stats)
        total_codes = sum(int(s.get("codes", 0)) for s in stats)

        identity_counts: dict[str, int] = {}
        for s in stats:
            ident = s.get("identity") or "unknown"
            identity_counts[ident] = identity_counts.get(ident, 0) + 1

        lines: list[str] = []
        lines.append("== File Centipede helper – Scrape stats ==")
        lines.append("")
        lines.append(f"Total scrapes recorded        : {count}")
        lines.append(
            f"Total scraped data (HTTP body): {self._format_bytes(total_bytes)}"
        )
        lines.append(
            f"Total activation codes scraped: {total_codes}"
        )

        if stats:
            first = stats[0]
            last = stats[-1]
            lines.append("")
            lines.append(f"First scrape (UTC)            : {first.get('at_utc')}")
            lines.append(f"First scrape (local)          : {first.get('at_local')}")
            lines.append(f"Last scrape (UTC)             : {last.get('at_utc')}")
            lines.append(f"Last scrape (local)           : {last.get('at_local')}")

        lines.append("")
        lines.append("[Browser identities]")
        if not identity_counts:
            lines.append("  (no scrapes recorded yet)")
        else:
            for ident, n in sorted(
                identity_counts.items(), key=lambda kv: kv[1], reverse=True
            ):
                lines.append(f"  {ident}: {n} scrape(s)")

        lines.append("")
        lines.append("[Per-scrape details]")
        if not stats:
            lines.append("  (no scrapes recorded yet)")
        else:
            for i, s in enumerate(stats, start=1):
                at_utc = s.get("at_utc", "?")
                at_local = s.get("at_local", "?")
                b = int(s.get("bytes", 0))
                codes = int(s.get("codes", 0))
                ident = s.get("identity") or "unknown"
                lines.append(
                    f"{i:02d}. UTC={at_utc}  local={at_local}  "
                    f"codes={codes}  size≈{self._format_bytes(b)}  ident={ident}"
                )

        return "\n".join(lines)

    def show_scrape_stats(self) -> None:
        text = self._build_scrape_stats_text()

        dlg = QDialog(self.c.window)
        dlg.setWindowTitle("Developer – Scrape stats")

        layout = QVBoxLayout(dlg)
        editor = QTextEdit(dlg)
        editor.setReadOnly(True)
        editor.setPlainText(text)
        layout.addWidget(editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
            | QDialogButtonBox.StandardButton.Reset,
            parent=dlg,
        )
        buttons.button(QDialogButtonBox.StandardButton.Reset).setText("Copy")
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)

        def do_copy() -> None:
            QApplication.clipboard().setText(text)

        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(do_copy)
        layout.addWidget(buttons)

        dlg.resize(700, 500)
        dlg.exec()

    # ------------------------------------------------------------------
    # Nag-screen helpers
    # ------------------------------------------------------------------

    def _update_nag_progress(self, codes_count: int) -> None:
        # Never nag in developer mode
        if getattr(self.c, "dev_mode_enabled", False):
            return
        if codes_count <= 0:
            return

        s = self.c.settings
        accumulated = s.value(REGISTER_NAG_PROGRESS_KEY, 0, type=int)
        accumulated = int(accumulated) + int(codes_count)

        if accumulated < REGISTER_NAG_THRESHOLD:
            s.setValue(REGISTER_NAG_PROGRESS_KEY, accumulated)
            return

        # Threshold reached or exceeded: show nag, then reset to 0
        self._show_register_nag(count=REGISTER_NAG_THRESHOLD)
        s.setValue(REGISTER_NAG_PROGRESS_KEY, 0)

    def _show_register_nag(self, count: int) -> None:
        box = QMessageBox(self.c.window)
        box.setWindowTitle("Thanks for using this helper")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            "You've now gotten "
            f"{count} activation codes through this application.\n\n"
            "I'm glad it's been useful — but the best way to support File Centipede "
            "is to purchase a lifetime activation code from the author.\n\n"
            "With a lifetime code, you can use File Centipede directly and no "
            "longer rely on this helper."
        )
        register_btn = box.addButton(
            "Open File Centipede site", QMessageBox.ButtonRole.AcceptRole
        )
        later_btn = box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is register_btn:
            QDesktopServices.openUrl(QUrl(REGISTER_URL))
        elif clicked is later_btn:
            # Counter already reset; we simply allow it to accumulate again.
            pass

    # ------------------------------------------------------------------
    # Purge cache & reset settings
    # ------------------------------------------------------------------

    def purge_cache_and_resync(self) -> None:
        c = self.c

        reply = QMessageBox.question(
            c.window,
            "Developer – Purge cache",
            "Delete all cached activation codes and re-sync from the site?\n\n"
            "This will remove the local JSON cache, clear scrape stats, and "
            "force a fresh online fetch.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            c.cache.purge()
        except Exception as exc:  # pragma: no cover - defensive
            QMessageBox.warning(
                c.window,
                "Developer",
                f"Failed to purge cache:\n{exc}",
            )
            return

        c.last_refresh_utc = None
        c.settings.setValue("last_refresh_utc", "")
        self._save_scrape_stats([])
        c.settings.setValue(REGISTER_NAG_PROGRESS_KEY, 0)

        c.window.refresh_from_cache(initial=True)
        c.update_refresh_ui()

        c._start_refresh_task(initial=True, use_network=True)

    def reset_settings_to_defaults(self) -> None:
        c = self.c

        reply = QMessageBox.question(
            c.window,
            "Developer – Reset settings",
            "Reset all app settings to defaults?\n\n"
            "This will clear stored preferences (timezone, refresh options, "
            "autostart, UI prefs, scrape stats, etc.).\n\n"
            "Cached activation codes will NOT be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        c.settings.clear()

        # These attributes are created in TrayController.__init__ and re-read
        # from QSettings; here we just restore sane defaults and persist them.
        c.icon_mode = "auto"
        c.auto_refresh_enabled = True
        c.open_on_start = True
        c.show_tooltip = True
        c.show_menu_info = True
        c._hide_to_tray_hint_shown = False
        c.last_refresh_utc = None

        from fc_token.config import (
            KEY_AUTO_REFRESH,
            KEY_ICON_MODE,
            KEY_REFRESH_INTERVAL,
            KEY_TIMEZONE,
        )

        c.settings.setValue(KEY_ICON_MODE, c.icon_mode)
        c.settings.setValue(KEY_AUTO_REFRESH, c.auto_refresh_enabled)
        c.settings.setValue("open_on_start", c.open_on_start)
        c.settings.setValue("show_tooltip", c.show_tooltip)
        c.settings.setValue("show_menu_info", c.show_menu_info)
        c.settings.setValue("hide_to_tray_hint_shown", c._hide_to_tray_hint_shown)
        c.settings.setValue("last_refresh_utc", "")
        c.settings.setValue(REGISTER_NAG_PROGRESS_KEY, 0)

        self._save_scrape_stats([])

        c._refresh_timezone_cache()
        c.update_timer()
        c.update_refresh_ui()
        c.update_tray_icon()

        QMessageBox.information(
            c.window,
            "Developer",
            "Settings reset to defaults. You may want to restart the app to "
            "verify first-run behavior.",
        )
