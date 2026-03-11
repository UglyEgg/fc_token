"""Formatting helpers for persisted refresh diagnostics."""

from __future__ import annotations

from datetime import datetime, tzinfo
import html

from fc_token.core.storage import DiagnosticsSnapshot, FetchRunRecord
from fc_token.models import UTC

_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def _format_utc_string(
    value: str | None, *, local_tz: tzinfo, local_tz_name: str
) -> str:
    """Convert a stored UTC timestamp string into a local display string."""
    if not value:
        return "—"
    try:
        parsed = datetime.strptime(value, _DATETIME_FMT).replace(tzinfo=UTC)
    except ValueError:
        return value
    return parsed.astimezone(local_tz).strftime(
        f"%Y-%m-%d %I:%M:%S %p ({local_tz_name})"
    )


def _format_run(run: FetchRunRecord, *, local_tz: tzinfo, local_tz_name: str) -> str:
    """Format one recent fetch run into a readable multi-line summary."""
    finished_local = run.finished_utc.astimezone(local_tz).strftime(
        f"%Y-%m-%d %I:%M:%S %p ({local_tz_name})"
    )
    status = "success" if run.success else "failure"

    lines = [
        f"- {finished_local} — {status}",
        f"  identity: {run.identity_label or '—'}",
        f"  bytes: {run.raw_bytes if run.raw_bytes is not None else '—'}",
        f"  codes: {run.code_count if run.code_count is not None else '—'}",
    ]

    if run.http_status is not None:
        lines.append(f"  http status: {run.http_status}")

    if run.error_kind or run.error_message:
        error_text = run.error_kind or "Error"
        if run.error_message:
            error_text = f"{error_text}: {run.error_message}"
        lines.append(f"  error: {error_text}")

    return "\n".join(lines)


def format_diagnostics_snapshot(
    snapshot: DiagnosticsSnapshot,
    *,
    local_tz: tzinfo,
    local_tz_name: str,
) -> str:
    """Render a persisted diagnostics snapshot into user-facing text."""
    lines = [
        f"Status: {snapshot.last_status or 'unknown'}",
        f"Last refresh: {_format_utc_string(snapshot.last_refresh_utc, local_tz=local_tz, local_tz_name=local_tz_name)}",
        f"Last success: {_format_utc_string(snapshot.last_success_refresh_utc, local_tz=local_tz, local_tz_name=local_tz_name)}",
        f"Last failure: {_format_utc_string(snapshot.last_failure_refresh_utc, local_tz=local_tz, local_tz_name=local_tz_name)}",
        f"Identity: {snapshot.last_identity_used or '—'}",
        f"Bytes received: {snapshot.last_scrape_raw_bytes if snapshot.last_scrape_raw_bytes is not None else '—'}",
        f"Codes parsed: {snapshot.last_scraped_codes_count}",
    ]

    if snapshot.last_error_kind or snapshot.last_error_message:
        error_text = snapshot.last_error_kind or "Error"
        if snapshot.last_error_message:
            error_text = f"{error_text}: {snapshot.last_error_message}"
        lines.append(f"Last error: {error_text}")
    else:
        lines.append("Last error: —")

    lines.append("")
    lines.append("Recent refresh runs:")

    if not snapshot.recent_fetch_runs:
        lines.append("- none recorded")
    else:
        for run in snapshot.recent_fetch_runs:
            lines.append(
                _format_run(run, local_tz=local_tz, local_tz_name=local_tz_name)
            )

    return "\n".join(lines)


def _status_label(status: str | None) -> str:
    normalized = (status or "unknown").lower()
    if normalized == "success":
        return "✅ success"
    if normalized == "failure":
        return "❌ failure"
    return f"⚪ {normalized}"


def _diag_line(label: str, value: str) -> str:
    return f"  • {label:<18}: {value}"


def format_diagnostics_snapshot_html(
    snapshot: DiagnosticsSnapshot,
    *,
    local_tz: tzinfo,
    local_tz_name: str,
) -> str:
    """Render persisted diagnostics into the same compact visual language as statistics."""
    last_refresh = _format_utc_string(
        snapshot.last_refresh_utc, local_tz=local_tz, local_tz_name=local_tz_name
    )
    last_success = _format_utc_string(
        snapshot.last_success_refresh_utc, local_tz=local_tz, local_tz_name=local_tz_name
    )
    last_failure = _format_utc_string(
        snapshot.last_failure_refresh_utc, local_tz=local_tz, local_tz_name=local_tz_name
    )

    if snapshot.last_error_kind or snapshot.last_error_message:
        error_text = snapshot.last_error_kind or "Error"
        if snapshot.last_error_message:
            error_text = f"{error_text}: {snapshot.last_error_message}"
    else:
        error_text = "—"

    lines: list[str] = []
    lines.append("== File Centipede helper – Diagnostics ==")
    lines.append("")
    lines.append("🩺 Refresh health")
    lines.append(_diag_line("Current status", _status_label(snapshot.last_status)))
    lines.append(_diag_line("Last refresh", last_refresh))
    lines.append(_diag_line("Last success", last_success))
    lines.append(_diag_line("Last failure", last_failure))
    lines.append("")
    lines.append("🌐 Last network activity")
    lines.append(_diag_line("Identity", snapshot.last_identity_used or "—"))
    lines.append(_diag_line("Bytes received", str(snapshot.last_scrape_raw_bytes) if snapshot.last_scrape_raw_bytes is not None else "—"))
    lines.append(_diag_line("Codes parsed", str(snapshot.last_scraped_codes_count)))
    lines.append("")
    lines.append("❗ Last error")
    lines.append(f"  • {error_text}")
    lines.append("")
    lines.append("🕓 Recent refresh runs")
    if not snapshot.recent_fetch_runs:
        lines.append("  (no refresh runs recorded yet)")
    else:
        for run in snapshot.recent_fetch_runs:
            finished_local = run.finished_utc.astimezone(local_tz).strftime(
                f"%Y-%m-%d %I:%M:%S %p ({local_tz_name})"
            )
            bits = [
                f"identity={run.identity_label or '—'}",
                f"bytes={run.raw_bytes if run.raw_bytes is not None else '—'}",
                f"codes={run.code_count if run.code_count is not None else '—'}",
            ]
            if run.http_status is not None:
                bits.append(f"http={run.http_status}")
            if run.error_kind or run.error_message:
                err = run.error_kind or "Error"
                if run.error_message:
                    err = f"{err}: {run.error_message}"
                bits.append(f"error={err}")
            lines.append(f"  • {finished_local} — {_status_label('success' if run.success else 'failure')}")
            lines.append(f"    {' • '.join(bits)}")

    import html as _html
    def colorize(line: str) -> str:
        if line.startswith("== "):
            return "<span style='color:#4A7BD6;'>" f"{_html.escape(line)}" "</span>"
        if line in (
            "🩺 Refresh health",
            "🌐 Last network activity",
            "❗ Last error",
            "🕓 Recent refresh runs",
        ):
            return "<span style='color:#D7BA7D;'>" f"{_html.escape(line)}" "</span>"
        return _html.escape(line)

    body = "\n".join(colorize(l) for l in lines)
    return (
        "<html><body>"
        "<pre style='font-family: monospace; font-size: 9pt;'>"
        f"{body}"
        "</pre>"
        "</body></html>"
    )
