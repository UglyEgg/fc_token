from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

ALLOWED_QUERY_PREFIXES = ("select", "with", "pragma")


def _open_readonly_connection(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name ASC"
    ).fetchall()
    return [str(r[0]) for r in rows]


def _fetch_scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return 0 if row is None else int(row[0])


def _fetch_pragma_scalar(conn: sqlite3.Connection, pragma_name: str):
    row = conn.execute(f"PRAGMA {pragma_name}").fetchone()
    if row is None:
        return None
    return row[0]


def _query_app_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def _safe_display(value) -> str:
    return "—" if value is None or value == "" else str(value)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, object]]:
    return [dict(row) for row in rows]


def _populate_table(widget: QTableWidget, rows: list[sqlite3.Row]) -> None:
    if not rows:
        widget.clear()
        widget.setRowCount(0)
        widget.setColumnCount(0)
        return
    headers = list(rows[0].keys())
    widget.clear()
    widget.setColumnCount(len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setRowCount(len(rows))
    for r_i, row in enumerate(rows):
        for c_i, header in enumerate(headers):
            item = QTableWidgetItem(_safe_display(row[header]))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            widget.setItem(r_i, c_i, item)
    widget.resizeColumnsToContents()


def _copy_selected_table(widget: QTableWidget) -> None:
    indexes = widget.selectedIndexes()
    if not indexes:
        return
    rows = sorted({idx.row() for idx in indexes})
    cols = sorted({idx.column() for idx in indexes})
    lines = []
    headers = [widget.horizontalHeaderItem(c).text() for c in cols]
    lines.append("\t".join(headers))
    for r in rows:
        vals = []
        for c in cols:
            item = widget.item(r, c)
            vals.append("" if item is None else item.text())
        lines.append("\t".join(vals))
    QApplication.clipboard().setText("\n".join(lines))


def _copy_all_table(widget: QTableWidget) -> None:
    if widget.rowCount() <= 0 or widget.columnCount() <= 0:
        return
    lines = []
    headers = [widget.horizontalHeaderItem(c).text() for c in range(widget.columnCount())]
    lines.append("\t".join(headers))
    for r in range(widget.rowCount()):
        vals = []
        for c in range(widget.columnCount()):
            item = widget.item(r, c)
            vals.append("" if item is None else item.text())
        lines.append("\t".join(vals))
    QApplication.clipboard().setText("\n".join(lines))


def _validate_query(sql: str) -> str | None:
    cleaned = sql.strip()
    if not cleaned:
        return "Enter a SELECT, WITH, or PRAGMA query."
    lowered = cleaned.lower()
    if not lowered.startswith(ALLOWED_QUERY_PREFIXES):
        return "Only read-only SELECT, WITH, or PRAGMA queries are allowed."
    blocked = ("insert", "update", "delete", "drop", "alter", "vacuum", "replace", "create ")
    if any(tok in lowered for tok in blocked):
        return "Mutating SQL statements are not allowed in the inspector."
    return None


class SQLiteExplorerDialog(QDialog):
    def __init__(self, parent: QWidget | None, db_path: Path) -> None:
        super().__init__(parent)
        self.db_path = Path(db_path)
        self._table_names: list[str] = []
        self._current_table_rows: list[sqlite3.Row] = []
        self._current_query_rows: list[sqlite3.Row] = []
        self.setWindowTitle("SQLite database inspector")
        self.resize(1040, 760)

        root = QVBoxLayout(self)
        tabs = QTabWidget(self)
        root.addWidget(tabs)

        self.overview_tab = QWidget(self)
        self.tables_tab = QWidget(self)
        self.query_tab = QWidget(self)
        tabs.addTab(self.overview_tab, "Overview")
        tabs.addTab(self.tables_tab, "Tables")
        tabs.addTab(self.query_tab, "Query")

        self._build_overview_tab()
        self._build_tables_tab()
        self._build_query_tab()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

        self._load_overview()
        self._load_table_names()
        self._load_selected_table()

    def _build_overview_tab(self) -> None:
        layout = QVBoxLayout(self.overview_tab)
        group = QGroupBox("Database summary", self.overview_tab)
        grid = QGridLayout(group)
        self.overview_labels = {}
        labels = [
            ("db_path", "Database path"),
            ("file_size", "File size"),
            ("tables", "Tables"),
            ("tokens", "Token rows"),
            ("fetch_runs", "Fetch run rows"),
            ("app_state", "App state rows"),
            ("last_refresh", "Last refresh"),
            ("last_success", "Last success"),
            ("last_failure", "Last failure"),
            ("page_size", "Page size"),
            ("page_count", "Page count"),
            ("freelist_count", "Freelist pages"),
            ("journal_mode", "Journal mode"),
            ("wal_autocheckpoint", "WAL auto-checkpoint"),
        ]
        for row, (key, title) in enumerate(labels):
            title_lbl = QLabel(f"<b>{title}</b>")
            value_lbl = QLabel("—")
            value_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value_lbl.setWordWrap(True)
            grid.addWidget(title_lbl, row, 0)
            grid.addWidget(value_lbl, row, 1)
            self.overview_labels[key] = value_lbl
        layout.addWidget(group)
        layout.addStretch()

    def _build_tables_tab(self) -> None:
        layout = QVBoxLayout(self.tables_tab)
        controls = QHBoxLayout()
        self.table_selector = QComboBox(self.tables_tab)
        self.table_selector.currentIndexChanged.connect(self._load_selected_table)
        controls.addWidget(QLabel("Table:"))
        controls.addWidget(self.table_selector)

        self.limit_selector = QComboBox(self.tables_tab)
        self.limit_selector.addItems(["50", "100", "250", "500"])
        self.limit_selector.setCurrentText("100")
        self.limit_selector.currentIndexChanged.connect(self._load_selected_table)
        controls.addWidget(QLabel("Rows:"))
        controls.addWidget(self.limit_selector)

        self.filter_edit = QLineEdit(self.tables_tab)
        self.filter_edit.setPlaceholderText("Optional text filter across visible columns")
        self.filter_edit.returnPressed.connect(self._load_selected_table)
        controls.addWidget(self.filter_edit, 1)

        refresh_btn = QPushButton("Refresh", self.tables_tab)
        refresh_btn.clicked.connect(self._load_selected_table)
        controls.addWidget(refresh_btn)

        copy_sel_btn = QPushButton("Copy selected", self.tables_tab)
        copy_sel_btn.clicked.connect(lambda: _copy_selected_table(self.table_widget))
        controls.addWidget(copy_sel_btn)

        copy_all_btn = QPushButton("Copy visible", self.tables_tab)
        copy_all_btn.clicked.connect(lambda: _copy_all_table(self.table_widget))
        controls.addWidget(copy_all_btn)

        export_json_btn = QPushButton("Export visible JSON…", self.tables_tab)
        export_json_btn.clicked.connect(self._export_visible_table_json)
        controls.addWidget(export_json_btn)

        export_csv_btn = QPushButton("Export visible CSV…", self.tables_tab)
        export_csv_btn.clicked.connect(self._export_visible_table_csv)
        controls.addWidget(export_csv_btn)

        layout.addLayout(controls)

        self.table_widget = QTableWidget(self.tables_tab)
        self.table_widget.setSortingEnabled(True)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_widget)

    def _build_query_tab(self) -> None:
        layout = QVBoxLayout(self.query_tab)
        self.query_editor = QPlainTextEdit(self.query_tab)
        self.query_editor.setPlainText("SELECT * FROM tokens ORDER BY start_utc DESC LIMIT 50;")
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        self.query_editor.setFont(font)
        self.query_editor.setMinimumHeight(140)
        layout.addWidget(self.query_editor)

        controls = QHBoxLayout()
        run_btn = QPushButton("Run query", self.query_tab)
        run_btn.clicked.connect(self._run_query)
        controls.addWidget(run_btn)
        copy_btn = QPushButton("Copy results", self.query_tab)
        copy_btn.clicked.connect(lambda: _copy_all_table(self.query_results))
        controls.addWidget(copy_btn)
        export_csv_btn = QPushButton("Export CSV…", self.query_tab)
        export_csv_btn.clicked.connect(self._export_query_csv)
        controls.addWidget(export_csv_btn)
        export_json_btn = QPushButton("Export JSON…", self.query_tab)
        export_json_btn.clicked.connect(self._export_query_json)
        controls.addWidget(export_json_btn)
        controls.addStretch()
        layout.addLayout(controls)

        self.query_error = QLabel("", self.query_tab)
        self.query_error.setStyleSheet("color: #c62828;")
        self.query_error.setWordWrap(True)
        layout.addWidget(self.query_error)

        self.query_results = QTableWidget(self.query_tab)
        self.query_results.setSortingEnabled(True)
        self.query_results.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.query_results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.query_results)

    def _load_table_names(self) -> None:
        try:
            conn = _open_readonly_connection(self.db_path)
        except Exception as exc:
            QMessageBox.critical(self, "SQLite database inspector", f"Failed to open database read-only:\n{exc}")
            return
        with conn:
            self._table_names = _fetch_table_names(conn)
        self.table_selector.blockSignals(True)
        self.table_selector.clear()
        self.table_selector.addItems(self._table_names)
        preferred = [name for name in ("tokens", "fetch_runs", "app_state") if name in self._table_names]
        if preferred:
            self.table_selector.setCurrentText(preferred[0])
        self.table_selector.blockSignals(False)

    def _load_overview(self) -> None:
        try:
            conn = _open_readonly_connection(self.db_path)
        except Exception as exc:
            QMessageBox.critical(self, "SQLite database inspector", f"Failed to open database read-only:\n{exc}")
            return
        with conn:
            tables = _fetch_table_names(conn)
            self.overview_labels["db_path"].setText(str(self.db_path))
            size = self.db_path.stat().st_size if self.db_path.exists() else 0
            self.overview_labels["file_size"].setText(f"{size:,} bytes")
            self.overview_labels["tables"].setText(", ".join(tables) if tables else "—")
            table_set = set(tables)
            self.overview_labels["tokens"].setText(
                str(_fetch_scalar(conn, "SELECT COUNT(*) FROM tokens")) if "tokens" in table_set else "—"
            )
            self.overview_labels["fetch_runs"].setText(
                str(_fetch_scalar(conn, "SELECT COUNT(*) FROM fetch_runs")) if "fetch_runs" in table_set else "—"
            )
            self.overview_labels["app_state"].setText(
                str(_fetch_scalar(conn, "SELECT COUNT(*) FROM app_state")) if "app_state" in table_set else "—"
            )
            if "app_state" in table_set:
                self.overview_labels["last_refresh"].setText(_safe_display(_query_app_state(conn, "last_refresh_utc")))
                self.overview_labels["last_success"].setText(_safe_display(_query_app_state(conn, "last_success_refresh_utc")))
                self.overview_labels["last_failure"].setText(_safe_display(_query_app_state(conn, "last_failure_refresh_utc")))
            else:
                self.overview_labels["last_refresh"].setText("—")
                self.overview_labels["last_success"].setText("—")
                self.overview_labels["last_failure"].setText("—")

            page_size = _fetch_pragma_scalar(conn, "page_size")
            page_count = _fetch_pragma_scalar(conn, "page_count")
            freelist_count = _fetch_pragma_scalar(conn, "freelist_count")
            journal_mode = _fetch_pragma_scalar(conn, "journal_mode")
            wal_autocheckpoint = _fetch_pragma_scalar(conn, "wal_autocheckpoint")
            self.overview_labels["page_size"].setText(_safe_display(page_size))
            self.overview_labels["page_count"].setText(_safe_display(page_count))
            self.overview_labels["freelist_count"].setText(_safe_display(freelist_count))
            self.overview_labels["journal_mode"].setText(_safe_display(journal_mode))
            self.overview_labels["wal_autocheckpoint"].setText(_safe_display(wal_autocheckpoint))

    def _load_selected_table(self) -> None:
        table_name = self.table_selector.currentText()
        if not table_name:
            _populate_table(self.table_widget, [])
            self._current_table_rows = []
            return
        limit = int(self.limit_selector.currentText())
        filter_text = self.filter_edit.text().strip()
        try:
            conn = _open_readonly_connection(self.db_path)
        except Exception as exc:
            QMessageBox.critical(self, "SQLite database inspector", f"Failed to open database read-only:\n{exc}")
            return
        with conn:
            rows = conn.execute(f'SELECT * FROM "{table_name}" ORDER BY ROWID DESC LIMIT ?', (limit,)).fetchall()
        if filter_text:
            ft = filter_text.lower()
            rows = [r for r in rows if any(ft in _safe_display(v).lower() for v in tuple(r))]
        self._current_table_rows = rows
        _populate_table(self.table_widget, rows)

    def _run_query(self) -> None:
        sql = self.query_editor.toPlainText()
        error = _validate_query(sql)
        if error:
            self.query_error.setText(error)
            self._current_query_rows = []
            _populate_table(self.query_results, [])
            return
        try:
            conn = _open_readonly_connection(self.db_path)
            with conn:
                rows = conn.execute(sql).fetchall()
        except Exception as exc:
            self.query_error.setText(str(exc))
            self._current_query_rows = []
            _populate_table(self.query_results, [])
            return
        self.query_error.setText("")
        self._current_query_rows = rows
        _populate_table(self.query_results, rows)

    def _export_visible_table_csv(self) -> None:
        self._export_rows_csv(self._current_table_rows, default_name="table_rows.csv")

    def _export_query_csv(self) -> None:
        self._export_rows_csv(self._current_query_rows, default_name="query_results.csv")

    def _export_visible_table_json(self) -> None:
        self._export_rows_json(self._current_table_rows, default_name="table_rows.json")

    def _export_query_json(self) -> None:
        self._export_rows_json(self._current_query_rows, default_name="query_results.json")

    def _export_rows_csv(self, rows: list[sqlite3.Row], *, default_name: str) -> None:
        if not rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export rows", default_name, "CSV Files (*.csv)")
        if not path:
            return
        headers = list(rows[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([row[h] for h in headers])

    def _export_rows_json(self, rows: list[sqlite3.Row], *, default_name: str) -> None:
        if not rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export rows", default_name, "JSON Files (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_rows_to_dicts(rows), fh, indent=2, ensure_ascii=False)
            fh.write("\n")


def show_sqlite_explorer_dialog(parent: QWidget | None, db_path: Path) -> None:
    dlg = SQLiteExplorerDialog(parent, db_path)
    dlg.exec()
