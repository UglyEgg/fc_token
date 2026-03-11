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


def _status_chip(status: str | None) -> str:
    normalized = (status or "unknown").lower()
    if normalized == "success":
        color = "#2e7d32"
        emoji = "✅"
    elif normalized == "failure":
        color = "#c62828"
        emoji = "❌"
    else:
        color = "#b26a00"
        emoji = "⚪"
    return f"<span style=\"color:{color}; font-weight:600;\">{emoji} {html.escape(normalized)}</span>"


def _row_html(label: str, value: str) -> str:
    return (
        "<tr>"
        f"<td style=\"padding:2px 12px 2px 0; color:#4A7BD6; font-weight:600;\">{html.escape(label)}</td>"
        f"<td style=\"padding:2px 0;\">{value}</td>"
        "</tr>"
    )


def format_diagnostics_snapshot_html(
    snapshot: DiagnosticsSnapshot,
    *,
    local_tz: tzinfo,
    local_tz_name: str,
) -> str:
    """Render persisted diagnostics into a compact HTML summary."""
    last_refresh = _format_utc_string(
        snapshot.last_refresh_utc, local_tz=local_tz, local_tz_name=local_tz_name
    )
    last_success = _format_utc_string(
        snapshot.last_success_refresh_utc, local_tz=local_tz, local_tz_name=local_tz_name
    )
    last_failure = _format_utc_string(
        snapshot.last_failure_refresh_utc, local_tz=local_tz, local_tz_name=local_tz_name
    )

    error_text = "—"
    if snapshot.last_error_kind or snapshot.last_error_message:
        error_text = html.escape(snapshot.last_error_kind or "Error")
        if snapshot.last_error_message:
            error_text = f"{error_text}: {html.escape(snapshot.last_error_message)}"

    sections: list[str] = []
    sections.append(
        "<h3 style=\"color:#4A7BD6; margin-bottom:6px;\">🩺 Refresh health</h3>"
        "<table style=\"margin-bottom:12px;\">"
        + _row_html("Current status", _status_chip(snapshot.last_status))
        + _row_html("Last refresh", html.escape(last_refresh))
        + _row_html("Last successful refresh", html.escape(last_success))
        + _row_html("Last failed refresh", html.escape(last_failure))
        + "</table>"
    )
    sections.append(
        "<h3 style=\"color:#D7BA7D; margin-bottom:6px;\">🌐 Last network activity</h3>"
        "<table style=\"margin-bottom:12px;\">"
        + _row_html("Identity", html.escape(snapshot.last_identity_used or "—"))
        + _row_html(
            "Bytes received",
            html.escape(str(snapshot.last_scrape_raw_bytes)) if snapshot.last_scrape_raw_bytes is not None else "—",
        )
        + _row_html("Codes parsed", html.escape(str(snapshot.last_scraped_codes_count)))
        + "</table>"
    )
    sections.append(
        "<h3 style=\"color:#C75C5C; margin-bottom:6px;\">❗ Last error</h3>"
        f"<div style=\"margin-bottom:12px;\">{error_text}</div>"
    )

    runs_html: list[str] = []
    if not snapshot.recent_fetch_runs:
        runs_html.append("<li>none recorded</li>")
    else:
        for run in snapshot.recent_fetch_runs:
            finished_local = run.finished_utc.astimezone(local_tz).strftime(
                f"%Y-%m-%d %I:%M:%S %p ({local_tz_name})"
            )
            run_status = "success" if run.success else "failure"
            run_chip = _status_chip(run_status)
            detail_bits = [
                f"identity: {html.escape(run.identity_label or '—')}",
                f"bytes: {run.raw_bytes if run.raw_bytes is not None else '—'}",
                f"codes: {run.code_count if run.code_count is not None else '—'}",
            ]
            if run.http_status is not None:
                detail_bits.append(f"http: {run.http_status}")
            if run.error_kind or run.error_message:
                err = html.escape(run.error_kind or "Error")
                if run.error_message:
                    err = f"{err}: {html.escape(run.error_message)}"
                detail_bits.append(f"error: {err}")
            runs_html.append(
                "<li style=\"margin-bottom:8px;\">"
                f"<div><strong>{html.escape(finished_local)}</strong> — {run_chip}</div>"
                f"<div style=\"margin-top:2px; color:#666;\">{' • '.join(detail_bits)}</div>"
                "</li>"
            )

    sections.append(
        "<h3 style=\"color:#6A5ACD; margin-bottom:6px;\">🕓 Recent refresh runs</h3>"
        "<ul style=\"padding-left:18px; margin-top:0;\">"
        + "".join(runs_html)
        + "</ul>"
    )

    return (
        "<html><body style=\"font-family: sans-serif; font-size: 10pt;\">"
        + "".join(sections)
        + "</body></html>"
    )
