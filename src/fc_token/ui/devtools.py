from __future__ import annotations

"""Developer tools and diagnostics for fc-token.

This module is only used behind the "Developer" menu. It exposes a
:class:`DevTools` helper that the :class:`TrayController` wires actions to.

Goals:
- Provide rich debug information about cache, timezones and scheduling.
- Expose "stats for geeks" about online scrapes.
- Offer safe operations such as purging the cache or resetting settings.
- Implement the user-facing File Centipede "please register" nag logic.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QFont
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


# Uptime / lifecycle tracking
INSTALL_TIMESTAMP_KEY = "lifecycle/install_utc"
TOTAL_FOREGROUND_SECONDS_KEY = "lifecycle/total_foreground_seconds"


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

    def _format_duration(self, seconds: float | None) -> str:
        """Human-friendly formatting for scrape durations."""
        if seconds is None:
            return "n/a"
        try:
            secs = float(seconds)
        except Exception:
            return "n/a"

        if secs < 0:
            secs = 0.0

        # Sub-second
        if secs < 1.0:
            return f"{secs * 1000.0:.0f} ms"

        minutes = int(secs // 60)
        rem = secs - minutes * 60
        if minutes == 0:
            return f"{rem:.1f} s"

        hours = minutes // 60
        minutes = minutes % 60
        if hours == 0:
            return f"{minutes:d} min {rem:.0f} s"

        return f"{hours:d} h {minutes:d} min"

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

        if (
            getattr(c, "next_refresh_deadline", None) is not None
            and c.auto_refresh_enabled
        ):
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
        code_font = QFont()
        code_font.setFamily("Monospace")
        editor.setFont(code_font)
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

    def _find_code_for_datetime(
        self, when_utc: datetime, codes: list
    ) -> Optional[object]:
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
        dt_edit.setDateTime(
            dt_edit.dateTime().fromString(
                now_local.strftime("%Y-%m-%d %H:%M:%S"), "yyyy-MM-dd HH:mm:ss"
            )
        )
        row.addWidget(dt_edit)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
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
                    f"{idx:02d}. {status} " f"code={getattr(code, 'code', '<?>')}"
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

    def record_scrape_stats(
        self, codes: list, duration_seconds: float | None = None
    ) -> None:
        """Record a single online scrape event for stats and nag logic.

        Called from TrayController._on_refresh_success when use_network=True.
        Uses metadata exposed on CodeCache (identity, body size, codes count).

        duration_seconds:
            Wall-clock scrape duration from "start network refresh" to
            "usable cache / UI updated", in seconds. Optional; when not
            provided, duration will be stored as null.
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

        # Normalise duration field
        duration_sec: float | None = None
        if duration_seconds is not None:
            try:
                duration_sec = float(duration_seconds)
            except Exception:
                duration_sec = None

        stats = self._load_scrape_stats()
        stats.append(
            {
                "at_utc": now_utc.isoformat(),
                "at_local": now_local.isoformat(),
                "bytes": int(raw_bytes),
                "codes": int(codes_count),
                "identity": identity,
                "duration_sec": duration_sec,
            }
        )

        if len(stats) > SCRAPE_STATS_MAX_ENTRIES:
            stats = stats[-SCRAPE_STATS_MAX_ENTRIES:]

        self._save_scrape_stats(stats)

        # Update nag logic based on number of activation codes scraped
        self._update_nag_progress(codes_count=int(codes_count))

    def _compute_duration_aggregates(
        self, stats: list[dict]
    ) -> tuple[float | None, float | None, float | None]:
        durations: list[float] = []
        for s in stats:
            d = s.get("duration_sec")
            try:
                if d is not None and float(d) > 0:
                    durations.append(float(d))
            except Exception:
                pass

        if not durations:
            return None, None, None

        durations_sorted = sorted(durations)
        n = len(durations_sorted)
        mid = n // 2
        if n % 2 == 1:
            median_val: float | None = durations_sorted[mid]
        else:
            median_val = 0.5 * (durations_sorted[mid - 1] + durations_sorted[mid])
        avg_val: float | None = sum(durations_sorted) / n
        last_val: float | None = durations[-1]
        return median_val, avg_val, last_val

    def _build_scrape_stats_text(self) -> str:
        """Build a rich scrape statistics report (developer view, HTML)."""
        import math
        from datetime import datetime, timezone

        stats = self._load_scrape_stats()
        total_scrapes = len(stats)

        # --- Basic aggregates ---
        total_bytes = sum(int(s.get("bytes", 0)) for s in stats)
        total_codes = sum(int(s.get("codes", 0)) for s in stats)

        # Outcomes: we currently log only successful scrapes
        if total_scrapes > 0:
            success_count = total_scrapes
            fail_count = 0
            success_rate_str = "100%"
        else:
            success_count = 0
            fail_count = 0
            success_rate_str = "n/a"

        # --- Durations & buckets ---
        durations: list[float] = []
        for s in stats:
            d = s.get("duration_sec")
            try:
                if d is not None and float(d) > 0:
                    durations.append(float(d))
            except Exception:
                pass

        median_val, avg_val, last_val = self._compute_duration_aggregates(stats)

        fastest_val = min(durations) if durations else None
        slowest_val = max(durations) if durations else None

        def fmt_sec(val: float | None) -> str:
            if val is None:
                return "n/a"
            try:
                return f"{float(val):.2f}"
            except Exception:
                return "n/a"

        median_str = fmt_sec(median_val)
        avg_str = fmt_sec(avg_val)
        last_str = fmt_sec(last_val)
        fastest_str = fmt_sec(fastest_val)
        slowest_str = fmt_sec(slowest_val)

        bucket_lt1 = bucket_1_2 = bucket_2_5 = bucket_5_10 = bucket_gt10 = 0
        for d in durations:
            if d < 1.0:
                bucket_lt1 += 1
            elif d < 2.0:
                bucket_1_2 += 1
            elif d < 5.0:
                bucket_2_5 += 1
            elif d < 10.0:
                bucket_5_10 += 1
            else:
                bucket_gt10 += 1

        # --- Scrape window / active days ---
        if stats:
            first_scrape_utc = stats[0].get("at_utc", "n/a")
            last_scrape_utc = stats[-1].get("at_utc", "n/a")

            day_counts: dict[str, int] = {}
            for s in stats:
                at_local = s.get("at_local") or ""
                day = at_local.split("T", 1)[0] if "T" in at_local else at_local[:10]
                if day:
                    day_counts[day] = day_counts.get(day, 0) + 1

            active_days = len(day_counts)
            if day_counts:
                most_day, most_count = max(day_counts.items(), key=lambda kv: kv[1])
                most_active_summary = f"{most_day} ({most_count} scrapes)"
            else:
                most_active_summary = "n/a"
        else:
            first_scrape_utc = "n/a"
            last_scrape_utc = "n/a"
            active_days = 0
            most_active_summary = "n/a"

        # --- Code coverage (same as compact stats) ---
        from datetime import timezone as _tzmod

        codes = self.c.cache.get_codes()
        if codes:
            now_utc = datetime.now(_tzmod.utc)
            earliest = min(code.start for code in codes)
            latest = max(code.end for code in codes)

            if earliest.tzinfo is None:
                earliest = earliest.replace(tzinfo=_tzmod.utc)
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=_tzmod.utc)

            local_zone = self.c._get_local_zone()
            earliest_cov_local = earliest.astimezone(local_zone).isoformat()
            latest_cov_local = latest.astimezone(local_zone).isoformat()

            span_seconds = max(0, int((latest - earliest).total_seconds()))
            total_span_str = (
                self._format_duration(float(span_seconds))
                if span_seconds > 0
                else "n/a"
            )

            until_exhaust_seconds = int((latest - now_utc).total_seconds())
            if until_exhaust_seconds <= 0:
                until_exhaust_str = "expired"
            else:
                until_exhaust_str = self._format_duration(float(until_exhaust_seconds))
        else:
            earliest_cov_local = "n/a"
            latest_cov_local = "n/a"
            total_span_str = "n/a"
            until_exhaust_str = "n/a"

        # --- Uptime (shared with compact stats) ---
        now_utc = datetime.now(timezone.utc)

        # Current session
        session_seconds = 0
        session_start = getattr(self.c, "session_started_utc", None)
        if isinstance(session_start, datetime):
            if session_start.tzinfo is None:
                session_start = session_start.replace(tzinfo=timezone.utc)
            session_seconds = max(0, int((now_utc - session_start).total_seconds()))
            current_session_str = self._format_duration(float(session_seconds))
        else:
            current_session_str = "n/a"

        # Since installation / first run
        s = self.c.settings
        install_iso = s.value("lifecycle/install_utc", "", type=str)
        first_run_local = "n/a"
        total_uptime_str = "n/a"
        longest_session_str = "n/a"  # Not tracked yet; placeholder

        try:
            if install_iso:
                install_dt = datetime.fromisoformat(install_iso)
                if install_dt.tzinfo is None:
                    install_dt = install_dt.replace(tzinfo=timezone.utc)
                local_zone = self.c._get_local_zone()
                first_run_local = install_dt.astimezone(local_zone).isoformat()

                raw_total = int(
                    s.value("lifecycle/total_foreground_seconds", 0, type=int)
                )
                total_seconds = max(0, raw_total + session_seconds)
                total_uptime_str = self._format_duration(float(total_seconds))
        except Exception:
            pass

        # --- Identity counts & entropy ---
        identity_counts: dict[str, int] = {}
        for srec in stats:
            ident = srec.get("identity") or "unknown"
            identity_counts[ident] = identity_counts.get(ident, 0) + 1

        if total_scrapes > 0 and identity_counts:
            probs = [n / total_scrapes for n in identity_counts.values()]
            entropy = 0.0
            for p in probs:
                if p > 0:
                    entropy -= p * math.log2(p)
            entropy_str = f"{entropy:.2f} bits"
        else:
            entropy_str = "n/a"

        # --- HTML helpers ---
        def esc(text: str) -> str:
            return (
                str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        # Per-identity lines
        if identity_counts:
            id_lines = [
                f"  {ident:<22} | {count} scrape(s)"
                for ident, count in sorted(
                    identity_counts.items(), key=lambda kv: kv[1], reverse=True
                )
            ]
        else:
            id_lines = ["  (no scrapes recorded yet)"]

        # Per-scrape log rows
        log_lines: list[str] = []
        for i, srec in enumerate(stats, start=1):
            at_utc = srec.get("at_utc", "?")
            at_local = srec.get("at_local", "?")
            codes_val = int(srec.get("codes", 0) or 0)
            raw_bytes = int(srec.get("bytes", 0) or 0)
            bytes_fmt = self._format_bytes(raw_bytes)
            ident = srec.get("identity") or "unknown"
            d = srec.get("duration_sec")
            d_str = fmt_sec(d if d is not None else None)

            log_lines.append(
                f"{i:02d}  {at_utc:<26}  {at_local:<26}  "
                f"{codes_val:5d}  {bytes_fmt:<9}  {ident:<10}  {d_str:>8}"
            )

        # Header line for log
        log_header = (
            "  #   UTC timestamp                 local timestamp               "
            "codes  size      UA         duration"
        )

        # --- Build HTML with light color highlights ---
        lines: list[str] = []
        lines.append(
            "<span style='color:#4A7BD6;'>"
            "==================== File Centipede helper – Scrape stats ===================="
            "</span>"
        )
        lines.append("")
        lines.append("<span style='color:#D7BA7D;'>OVERVIEW</span>")
        lines.append(f"  Scrapes recorded         | {total_scrapes}")
        lines.append(f"  Activation codes scraped | {total_codes}")
        lines.append(f"  Data downloaded          | {self._format_bytes(total_bytes)}")
        lines.append("")
        lines.append("<span style='color:#D7BA7D;'>OUTCOMES</span>")
        lines.append(f"  Successful scrapes       | {success_count}")
        lines.append(f"  Failed scrapes           | {fail_count}")
        lines.append(f"  Success rate             | {success_rate_str}")
        lines.append("")
        lines.append("<span style='color:#D7BA7D;'>UPTIME</span>")
        lines.append(f"  First run (local)        | {first_run_local}")
        lines.append(f"  Current session          | {current_session_str}")
        lines.append(f"  Total uptime             | {total_uptime_str}")
        lines.append(f"  Longest single session   | {longest_session_str}")
        lines.append("")
        lines.append("<span style='color:#D7BA7D;'>DURATIONS (s)</span>")
        lines.append(f"  Fastest scrape           | {fastest_str}")
        lines.append(f"  Slowest scrape           | {slowest_str}")
        lines.append(f"  Median duration          | {median_str}")
        lines.append(f"  Average duration         | {avg_str}")
        lines.append(f"  Last scrape              | {last_str}")
        lines.append("")
        lines.append(
            "<span style='color:#D7BA7D;'>DURATION HISTOGRAM (# scrapes)</span>"
        )
        lines.append(f"  <1s    : {bucket_lt1}")
        lines.append(f"  1–2s   : {bucket_1_2}")
        lines.append(f"  2–5s   : {bucket_2_5}")
        lines.append(f"  5–10s  : {bucket_5_10}")
        lines.append(f"  >10s   : {bucket_gt10}")
        lines.append("")
        lines.append("<span style='color:#D7BA7D;'>SCRAPE WINDOW</span>")
        lines.append(f"  First scrape (UTC)       | {first_scrape_utc}")
        lines.append(f"  Last scrape  (UTC)       | {last_scrape_utc}")
        lines.append(f"  Active scrape days       | {active_days}")
        lines.append(f"  Most active day          | {most_active_summary}")
        lines.append("")
        lines.append("<span style='color:#D7BA7D;'>CODE COVERAGE</span>")
        lines.append(f"  Earliest cached start    | {earliest_cov_local}")
        lines.append(f"  Latest cached end        | {latest_cov_local}")
        lines.append(f"  Total coverage span      | {total_span_str}")
        lines.append(f"  Time until exhaustion    | {until_exhaust_str}")
        lines.append("")
        lines.append("<span style='color:#D7BA7D;'>BROWSER IDENTITIES</span>")
        lines.extend(id_lines)
        lines.append(f"  Diversity (entropy)      | {entropy_str}")
        lines.append("")
        lines.append("<span style='color:#D7BA7D;'>PER-SCRAPE LOG</span>")
        lines.append(log_header)
        if log_lines:
            lines.extend(log_lines)
        else:
            lines.append("  (no scrapes recorded yet)")
        lines.append("")

        # Wrap in <pre> with monospace
        body = "\n".join(esc(line) for line in lines)
        # Re-inject span tags (we escaped them above)
        body = body.replace("&lt;span", "<span").replace("span&gt;", "span>")

        html = (
            "<html><body>"
            "<pre style='font-family: monospace; font-size: 9pt;'>"
            f"{body}"
            "</pre>"
            "</body></html>"
        )
        return html

    def show_scrape_stats(self) -> None:
        text = self._build_scrape_stats_text()  # now HTML

        dlg = QDialog(self.c.window)
        dlg.setWindowTitle("Developer – Scrape statistics")

        layout = QVBoxLayout(dlg)
        editor = QTextEdit(dlg)
        editor.setReadOnly(True)
        editor.setHtml(text)
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
            QApplication.clipboard().setText(editor.toPlainText())

        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(do_copy)
        layout.addWidget(buttons)

        dlg.resize(900, 600)
        dlg.exec()

    # ------------------------------------------------------------------
    # Compact stats for Easter egg (non-dev)
    # ------------------------------------------------------------------

    def build_compact_stats_text(self) -> str:
        """Compact, user-friendly summary of scrape stats (for the egg Easter egg)."""
        import math

        stats = self._load_scrape_stats()
        total_scrapes = len(stats)

        # Basic aggregates from existing helpers
        total_bytes = sum(int(s.get("bytes", 0)) for s in stats)
        total_codes = sum(int(s.get("codes", 0)) for s in stats)

        identity_counts: dict[str, int] = {}
        durations: list[float] = []
        for s in stats:
            ident = s.get("identity") or "unknown"
            identity_counts[ident] = identity_counts.get(ident, 0) + 1
            d = s.get("duration_sec")
            try:
                if d is not None and float(d) > 0:
                    durations.append(float(d))
            except Exception:
                pass

        median_val, avg_val, last_val = self._compute_duration_aggregates(stats)

        # Fastest / slowest (best / worst) duration from the same durations list
        if durations:
            fastest_val = min(durations)
            slowest_val = max(durations)
        else:
            fastest_val = None
            slowest_val = None

        median_str = self._format_duration(median_val)
        avg_str = self._format_duration(avg_val)
        last_str = self._format_duration(last_val)
        fastest_str = self._format_duration(fastest_val)
        slowest_str = self._format_duration(slowest_val)

        # Reliability: currently we only log *successful* scrapes.
        # If stats exist, treat them all as successes and 0 failures.
        if total_scrapes > 0:
            success_count = total_scrapes
            fail_count = 0
            success_rate_str = "100%"
        else:
            success_count = 0
            fail_count = 0
            success_rate_str = "n/a"

        # Coverage & time to exhaustion from the cached codes
        codes = self.c.cache.get_codes()
        if codes:
            now_utc = datetime.now(timezone.utc)
            earliest = min(code.start for code in codes)
            latest = max(code.end for code in codes)

            # Normalise to UTC
            if earliest.tzinfo is None:
                earliest = earliest.replace(tzinfo=timezone.utc)
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)

            span_seconds = max(0, int((latest - earliest).total_seconds()))
            total_span_str = (
                self._format_duration(span_seconds) if span_seconds > 0 else "n/a"
            )

            until_exhaust_seconds = int((latest - now_utc).total_seconds())
            if until_exhaust_seconds <= 0:
                until_exhaust_str = "expired"
            else:
                until_exhaust_str = self._format_duration(until_exhaust_seconds)
        else:
            total_span_str = "n/a"
            until_exhaust_str = "n/a"

        # Uptime
        now_utc = datetime.now(timezone.utc)

        # This session: based on controller.session_started_utc
        session_seconds = 0
        session_start = getattr(self.c, "session_started_utc", None)
        if isinstance(session_start, datetime):
            if session_start.tzinfo is None:
                session_start = session_start.replace(tzinfo=timezone.utc)
            session_seconds = max(0, int((now_utc - session_start).total_seconds()))
            current_session_str = self._format_duration(float(session_seconds))
        else:
            current_session_str = "n/a"

        # Since installation: use INSTALL_TIMESTAMP_KEY + TOTAL_FOREGROUND_SECONDS_KEY
        settings = self.c.settings
        install_iso = settings.value(INSTALL_TIMESTAMP_KEY, "", type=str)
        try:
            if install_iso:
                install_dt = datetime.fromisoformat(install_iso)
                if install_dt.tzinfo is None:
                    install_dt = install_dt.replace(tzinfo=timezone.utc)
                raw_total = int(
                    settings.value(TOTAL_FOREGROUND_SECONDS_KEY, 0, type=int)
                )
                # Include current session so the value is live
                total_seconds = max(0, raw_total + session_seconds)
                total_uptime_str = self._format_duration(float(total_seconds))
            else:
                total_uptime_str = "n/a"
        except Exception:
            total_uptime_str = "n/a"

        # User-agent rotation entropy (diversity score)
        if total_scrapes > 0 and identity_counts:
            probs = [n / total_scrapes for n in identity_counts.values()]
            entropy = 0.0
            for p in probs:
                if p > 0:
                    entropy -= p * math.log2(p)
            entropy_str = f"{entropy:.2f} bits"
        else:
            entropy_str = "n/a"

        # Identity usage lines
        if identity_counts:
            # Sort by usage count, descending
            id_lines = [
                f"      {ident}: {count}"
                for ident, count in sorted(
                    identity_counts.items(), key=lambda kv: kv[1], reverse=True
                )
            ]
            identity_block = "\n".join(id_lines)
        else:
            identity_block = "      (no scrapes recorded yet)"

        lines: list[str] = []
        lines.append("== File Centipede helper – Status ==")
        lines.append("")
        lines.append("📦 Scrapes & data")
        lines.append(f"  • Scrapes recorded   : {total_scrapes}")
        lines.append(f"  • Activation codes   : {total_codes}")
        lines.append(f"  • Data downloaded    : {self._format_bytes(total_bytes)}")
        lines.append("")
        lines.append("🚀 Performance")
        lines.append(f"  • Typical (median)   : {median_str}")
        lines.append(f"  • Average            : {avg_str}")
        lines.append(f"  • Fastest / slowest  : {fastest_str} / {slowest_str}")
        lines.append(f"  • Last scrape        : {last_str}")
        lines.append("")
        lines.append("✅ Reliability")
        lines.append(f"  • Successful / failed: {success_count} / {fail_count}")
        lines.append(f"  • Success rate       : {success_rate_str}")
        lines.append("")
        lines.append("🗺 Coverage")
        lines.append(f"  • Coverage span      : {total_span_str}")
        lines.append(f"  • Time to exhaustion : {until_exhaust_str}")
        lines.append("")
        lines.append("⏱ Uptime")
        lines.append(f"  • This session       : {current_session_str}")
        lines.append(f"  • Since installation : {total_uptime_str}")
        lines.append("")
        lines.append("🧬 User-agent rotation")
        lines.append(f"  • Diversity score    : {entropy_str}")
        lines.append("  • Usage counts       :")
        lines.append(identity_block)
        lines.append("")
        lines.append("(Stats are kept locally on this machine only.)")

        import html as _html

        plain_lines = lines

        def colorize(line: str) -> str:
            if line.startswith("== "):
                return "<span style='color:#4A7BD6;'>" f"{_html.escape(line)}" "</span>"
            if line in (
                "📦 Scrapes & data",
                "🚀 Performance",
                "✅ Reliability",
                "🗺 Coverage",
                "⏱ Uptime",
                "🧬 User-agent rotation",
            ):
                return "<span style='color:#D7BA7D;'>" f"{_html.escape(line)}" "</span>"
            return _html.escape(line)

        body = "\n".join(colorize(l) for l in plain_lines)
        html = (
            "<html><body>"
            "<pre style='font-family: monospace; font-size: 9pt;'>"
            f"{body}"
            "</pre>"
            "</body></html>"
        )
        return html

    def show_compact_stats_dialog(self) -> None:
        """Show a small, read-only status dialog (for non-dev Easter egg)."""
        text = self.build_compact_stats_text()  # now HTML

        dlg = QDialog(self.c.window)
        dlg.setWindowTitle("File Centipede helper – Status")

        layout = QVBoxLayout(dlg)
        editor = QTextEdit(dlg)
        editor.setReadOnly(True)
        editor.setHtml(text)
        layout.addWidget(editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            parent=dlg,
        )
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)

        dlg.resize(600, 260)
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
