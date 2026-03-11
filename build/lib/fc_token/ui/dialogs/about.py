from __future__ import annotations

from importlib.resources import files
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QPixmap, QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from fc_token.config import (
    APP_NAME,
    APP_VERSION,
    FILE_CENTIPEDE_URL,
    FILE_CENTIPEDE_BUY_URL,
    PROJECT_URL,
)
from fc_token.icons import load_app_icon

if TYPE_CHECKING:  # pragma: no cover
    from fc_token.ui.tray import TrayController


LICENSE_URL = "https://www.gnu.org/licenses/agpl-3.0.html#license-text"

# Keep a single instance of the About dialog.
_about_dialog: QDialog | None = None


class ClickableLabel(QLabel):
    """A QLabel that emits a clicked() signal when left-clicked."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def show_about_dialog(
    parent: QWidget | None = None,
    tray: "TrayController | None" = None,
) -> None:
    """Show the About dialog (singleton).

    If an About window is already open, bring it to front instead of creating
    a second one.
    """
    global _about_dialog

    # If there's an existing visible dialog, just focus it.
    if _about_dialog is not None:
        if _about_dialog.isVisible():
            _about_dialog.raise_()
            _about_dialog.activateWindow()
            return
        else:
            # It exists but isn't visible anymore; clean it up.
            _about_dialog.deleteLater()
            _about_dialog = None

    dlg = QDialog(parent)
    dlg.setWindowTitle(f"About {APP_NAME}")
    dlg.setMinimumWidth(420)

    # When this dialog finishes, clear the global reference.
    def on_finished(_result: int) -> None:
        global _about_dialog
        _about_dialog = None

    dlg.finished.connect(on_finished)

    layout = QVBoxLayout(dlg)

    # ------------------------------------------------------------
    # Header: App icon + Title / Version
    # ------------------------------------------------------------
    header = QHBoxLayout()

    app_icon = load_app_icon()
    if not app_icon.isNull():
        icon_lbl = QLabel()
        icon_lbl.setPixmap(app_icon.pixmap(48, 48))
        header.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignTop)

    header_text_layout = QVBoxLayout()

    # Title
    title_lbl = QLabel(f"<h2>{APP_NAME}</h2>")
    title_lbl.setTextFormat(Qt.TextFormat.RichText)
    header_text_layout.addWidget(title_lbl)

    # Version under title, slightly larger than body text (from config)
    version_lbl = QLabel(f'<span style="font-size:11pt;">Version {APP_VERSION}</span>')
    version_lbl.setTextFormat(Qt.TextFormat.RichText)
    header_text_layout.addWidget(version_lbl)

    header_text_layout.addStretch()
    header.addLayout(header_text_layout)
    header.addStretch()

    layout.addLayout(header)

    # ------------------------------------------------------------
    # Description block with separators
    # ------------------------------------------------------------
    desc_html = """
        <hr/>
        <p>This helper fetches and manages File Centipede activation codes
        and presents them in a KDE/Plasma-friendly tray application.</p>

        <p><i>This application only fetches trial activation codes from the
        official File Centipede website at a limited refresh rate, and
        operates offline using cached codes whenever possible. It does not
        generate, crack, or bypass license keys.</i></p>
        <hr/>
    """

    desc_lbl = QLabel(desc_html)
    desc_lbl.setWordWrap(True)
    desc_lbl.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(desc_lbl)

    # ------------------------------------------------------------
    # File Centipede links + "ugly egg" logo row
    # ------------------------------------------------------------
    fc_row = QHBoxLayout()

    links_layout = QVBoxLayout()

    visit_lbl = QLabel(
        f'<b><a href="{FILE_CENTIPEDE_URL}">Visit File Centipede Home</a></b>'
    )
    visit_lbl.setTextFormat(Qt.TextFormat.RichText)
    visit_lbl.setOpenExternalLinks(True)
    links_layout.addWidget(visit_lbl)

    buy_lbl = QLabel(
        f'<b><a href="{FILE_CENTIPEDE_BUY_URL}">Buy File Centipede</a></b>'
    )
    buy_lbl.setTextFormat(Qt.TextFormat.RichText)
    buy_lbl.setOpenExternalLinks(True)
    links_layout.addWidget(buy_lbl)

    links_layout.addStretch()
    fc_row.addLayout(links_layout, stretch=1)

    # Right side: the ugly egg logo (clickable)
    logo_lbl = ClickableLabel()
    logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    logo_pix_full: QPixmap | None = None
    try:
        logo_path = files("fc_token.resources").joinpath("uglyegg.png")
        pix_full = QPixmap(str(logo_path))
        if not pix_full.isNull():
            logo_pix_full = pix_full
            small = pix_full.scaledToWidth(
                48, Qt.TransformationMode.SmoothTransformation
            )
            logo_lbl.setPixmap(small)
    except Exception:
        logo_pix_full = None

    fc_row.addWidget(
        logo_lbl,
        alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    )

    layout.addLayout(fc_row)

    # Clicking the egg shows an enlarged version of the image in a popup.
    # In the enlarged dialog, hovering shows a tooltip; clicking runs the
    # compact stats Easter egg (if dev_tools is available on the tray).
    def show_large_logo() -> None:
        nonlocal logo_pix_full
        if logo_pix_full is None:
            return

        logo_dlg = QDialog(dlg)
        logo_dlg.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Popup
            | Qt.WindowType.NoDropShadowWindowHint
        )
        logo_dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        v = QVBoxLayout(logo_dlg)

        # Big clickable egg
        big_lbl = ClickableLabel()
        big_pix = logo_pix_full.scaledToWidth(
            256, Qt.TransformationMode.SmoothTransformation
        )
        big_lbl.setPixmap(big_pix)
        big_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Easter-egg tooltip (always shown, dev or non-dev)
        big_lbl.setToolTip("Some eggs are just ugly")
        v.addWidget(big_lbl)

        def on_big_clicked() -> None:
            # Close the large-logo dialog first
            logo_dlg.accept()
            # Then show the compact stats if available
            if tray is not None and getattr(tray, "dev_tools", None) is not None:
                tray.dev_tools.show_compact_stats_dialog()

        big_lbl.clicked.connect(on_big_clicked)

        close_btn_logo = QPushButton("Close")
        close_btn_logo.clicked.connect(logo_dlg.accept)
        v.addWidget(close_btn_logo, alignment=Qt.AlignmentFlag.AlignHCenter)

        logo_dlg.resize(320, 320)
        logo_dlg.exec()

    logo_lbl.clicked.connect(show_large_logo)

    # ------------------------------------------------------------
    # License line under the File Centipede links row
    # ------------------------------------------------------------
    license_lbl = QLabel(
        f"<b>License:</b> "
        f'<a href="{LICENSE_URL}">GNU Affero General Public License v3.0 (AGPL-3.0)</a>'
    )
    license_lbl.setTextFormat(Qt.TextFormat.RichText)
    license_lbl.setOpenExternalLinks(True)
    layout.addWidget(license_lbl)

    # ------------------------------------------------------------
    # Bottom: GitHub (left) + Close (right)
    # ------------------------------------------------------------
    btn_row = QHBoxLayout()

    project_url = PROJECT_URL

    if project_url:
        github_btn = QPushButton("GitHub")

        def open_github() -> None:
            QDesktopServices.openUrl(QUrl(project_url))

        github_btn.clicked.connect(open_github)
        btn_row.addWidget(github_btn)

    # Stretch after GitHub so Close is pushed to the right
    btn_row.addStretch()

    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    # Show and keep the global reference
    _about_dialog = dlg
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
