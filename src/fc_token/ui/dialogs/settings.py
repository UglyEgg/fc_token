from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QMessageBox,
)

from fc_token.config import DEFAULT_TIMEZONE
from fc_token.ui.utils import get_local_zone_name

if TYPE_CHECKING:
    from fc_token.ui.tray import TrayController


def run_settings_dialog(parent, tray: "TrayController") -> None:
    """Open the unified Settings dialog."""
    dlg = SettingsDialog(parent, tray)
    dlg.exec()


class SettingsDialog(QDialog):
    """Unified Settings window for File Centipede helper."""

    def __init__(self, parent, tray: "TrayController") -> None:
        super().__init__(parent)
        self.tray = tray

        self.setWindowTitle("Settings")
        self.setModal(True)

        main_layout = QVBoxLayout(self)

        # --- Refresh group -------------------------------------------------
        refresh_group = QGroupBox("Refresh")
        refresh_layout = QVBoxLayout(refresh_group)

        self.chk_auto_refresh = QCheckBox(
            "Enable daily automatic refresh (recommended)"
        )
        self.chk_auto_refresh.setChecked(tray.auto_refresh_enabled)
        refresh_layout.addWidget(self.chk_auto_refresh)

        hint_label = QLabel(
            "When enabled, the helper will refresh activation codes once per day. To "
            "avoid unnecessary traffic, it will not contact the File Centipede website "
            "while any cached activation codes remain valid. After the final cached "
            "code expires, daily online refreshes resume."
        )
        hint_label.setWordWrap(True)
        refresh_layout.addWidget(hint_label)

        main_layout.addWidget(refresh_group)

        # --- Time & appearance group --------------------------------------
        time_group = QGroupBox("Time && appearance")
        time_layout = QVBoxLayout(time_group)

        # Timezone row
        tz_row = QHBoxLayout()
        self.lbl_timezone = QLabel()
        tz_row.addWidget(self.lbl_timezone)

        self.btn_change_tz = QPushButton("Change timezone…")
        self.btn_change_tz.clicked.connect(self._on_change_timezone_clicked)
        tz_row.addWidget(self.btn_change_tz)

        time_layout.addLayout(tz_row)
        self._update_timezone_label()

        # Tray icon theme (stacked radios)
        icon_group = QGroupBox("Tray icon theme")
        icon_layout = QVBoxLayout(icon_group)

        self.radio_icon_auto = QRadioButton("Auto (system theme)")
        self.radio_icon_light = QRadioButton("Light icon")
        self.radio_icon_dark = QRadioButton("Dark icon")

        icon_mode = tray.icon_mode
        if icon_mode == "light":
            self.radio_icon_light.setChecked(True)
        elif icon_mode == "dark":
            self.radio_icon_dark.setChecked(True)
        else:
            self.radio_icon_auto.setChecked(True)

        icon_layout.addWidget(self.radio_icon_auto)
        icon_layout.addWidget(self.radio_icon_light)
        icon_layout.addWidget(self.radio_icon_dark)

        time_layout.addWidget(icon_group)

        main_layout.addWidget(time_group)

        # --- Integration & UI group ---------------------------------------
        integration_group = QGroupBox("Integration && UI")
        integration_layout = QVBoxLayout(integration_group)

        # Autostart
        self.chk_autostart = QCheckBox("Start on login")
        self.chk_autostart.setChecked(tray.is_autostart_enabled())
        integration_layout.addWidget(self.chk_autostart)

        # Open main window on start
        self.chk_open_on_start = QCheckBox("Open main window on start")
        self.chk_open_on_start.setChecked(getattr(tray, "open_on_start", True))
        integration_layout.addWidget(self.chk_open_on_start)

        # UI visibility
        self.chk_show_tooltip = QCheckBox("Show detailed status tooltip")
        self.chk_show_tooltip.setChecked(tray.show_tooltip)
        integration_layout.addWidget(self.chk_show_tooltip)

        self.chk_show_menu_info = QCheckBox("Show status submenu in tray menu")
        self.chk_show_menu_info.setChecked(tray.show_menu_info)
        integration_layout.addWidget(self.chk_show_menu_info)

        # Uninstall integration
        self.btn_uninstall = QPushButton("Remove launcher & tray icons…")
        self.btn_uninstall.clicked.connect(self._on_uninstall_clicked)
        integration_layout.addWidget(self.btn_uninstall)

        main_layout.addWidget(integration_group)

        # --- Advanced group ------------------------------------------------
        advanced_group = QGroupBox("Advanced")
        advanced_layout = QVBoxLayout(advanced_group)

        self.btn_clear_cache = QPushButton("Clear activation cache…")
        self.btn_clear_cache.clicked.connect(self._on_clear_cache_clicked)
        advanced_layout.addWidget(self.btn_clear_cache)

        advanced_hint = QLabel(
            "Clears all locally cached activation codes. Online refreshes are still "
            "limited by the application's internal refresh rules."
        )
        advanced_hint.setWordWrap(True)
        advanced_layout.addWidget(advanced_hint)

        main_layout.addWidget(advanced_group)

        # --- Dialog buttons ------------------------------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply_and_close)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self.setLayout(main_layout)

        # Comfortable default size
        self.resize(640, 540)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _update_timezone_label(self) -> None:
        tz_name = get_local_zone_name(DEFAULT_TIMEZONE)
        self.lbl_timezone.setText(f"Timezone: {tz_name}")

    def _on_change_timezone_clicked(self) -> None:
        # Delegate to tray's existing logic
        self.tray.change_timezone()
        self._update_timezone_label()

    def _on_uninstall_clicked(self) -> None:
        self.tray.uninstall_integration()

    def _on_clear_cache_clicked(self) -> None:
        """Advanced: clear activation cache with explanatory confirmation."""
        next_allowed_utc, remaining_sec = self.tray.get_next_allowed_refresh_info()

        if next_allowed_utc is None or remaining_sec is None or remaining_sec <= 0:
            message = (
                "Clear all locally cached activation codes?\n\n"
                "The helper will attempt to fetch new codes the next time you "
                "refresh or when the daily automatic refresh runs, subject to "
                "network availability."
            )
        else:
            from fc_token.ui.utils import get_local_zone

            local_zone = get_local_zone(DEFAULT_TIMEZONE)
            next_local = next_allowed_utc.astimezone(local_zone)
            next_time_str = next_local.strftime("%b %d, %Y %I:%M %p")
            human_remaining = self.tray._format_interval_seconds(remaining_sec)

            message = (
                "Clear all locally cached activation codes?\n\n"
                f"If you clear the cache now, the helper will not be allowed to "
                f"fetch new codes for about {human_remaining}, until around "
                f"{next_time_str}, due to its refresh limit.\n\n"
                "During that time you may be left without valid activation codes."
            )

        reply = QMessageBox.question(
            self,
            "Clear activation cache",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.tray.window.purge_cache()
            QMessageBox.information(
                self,
                "Cache cleared",
                "Activation cache has been cleared.",
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to clear activation cache:\n{exc}",
            )

    def _apply_and_close(self) -> None:
        # Refresh group
        auto_refresh_enabled = self.chk_auto_refresh.isChecked()
        self.tray.toggle_auto_refresh(auto_refresh_enabled)

        # Time & appearance: icon mode
        if self.radio_icon_light.isChecked():
            self.tray.set_icon_mode("light")
        elif self.radio_icon_dark.isChecked():
            self.tray.set_icon_mode("dark")
        else:
            self.tray.set_icon_mode("auto")

        # Integration & UI
        autostart_enabled = self.chk_autostart.isChecked()
        self.tray.set_autostart_enabled(autostart_enabled)

        # Open main window on start
        self.tray.toggle_open_on_start(self.chk_open_on_start.isChecked())

        self.tray.toggle_show_tooltip(self.chk_show_tooltip.isChecked())
        self.tray.toggle_show_menu_info(self.chk_show_menu_info.isChecked())

        self.accept()
