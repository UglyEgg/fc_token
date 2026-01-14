# File Centipede Activation Helper

**File Centipede Activation Helper** is a small KDE/Plasma-friendly tray utility that keeps your File Centipede trial activation codes up to date. It runs in the system tray, periodically scrapes the official activation page, and lets you quickly copy the current valid code.

---

## Features

- 🖥️ **KDE/Plasma-friendly tray application**

  - Close to tray, quit from tray menu.
  - Uses duck-themed icons for both window and tray.
  - Dark/light/auto tray icon modes.

- 🔁 **Automatic refresh (offline-first)**

  - Daily auto-refresh option, with manual “Refresh now” from the tray menu.
  - Skips network scrapes while cached codes are still valid.
  - Enforces a minimum 6-hour gap between online scrapes.

- 📅 **Future codes browser**

  - View all cached codes and their validity windows.
  - Double-click any row to see the full activation code.

- 💾 **On-disk cache**

  - Codes are cached locally (UTC timestamps).
  - Expired entries are automatically dropped.
  - Cache can be purged from the tray menu.

- 🌐 **Time-zone aware**

  - All scheduling and validity logic is done in UTC.
  - Human-facing timestamps are shown in your local timezone.

---

## Installation

### 1. Requirements

- Python **3.13+**
- A Linux desktop with a system tray (KDE/Plasma recommended).
- `PyQt6` and `requests` (pulled in automatically when you install the package).

### 2. Install from source (pip / pipx / uv)

From the project root:

```bash
# venv + pip
python -m venv .venv
source .venv/bin/activate
pip install .

# or with pipx
pipx install .

# or with uv (if you use it)
uv tool install .
```

This installs the `fc-token` console script on your `$PATH`.

You can now run:

```bash
fc-token
```

and the tray icon should appear.

### 3. (Optional) Install desktop launcher & icons

To integrate with your desktop’s application launcher and icon theme, use the provided installer script:

```bash
# Install for the current user (~/.local/share)
python -m fc_token.installer install --user

# Install system-wide (e.g. /usr/local/share) – requires appropriate permissions
sudo python -m fc_token.installer install --system
```

To uninstall:

```bash
python -m fc_token.installer uninstall --user
# or
sudo python -m fc_token.installer uninstall --system
```

Note: the Python module name uses an underscore (`fc_token`), even though the package name
uses a hyphen (`fc-token`).

This installs:

- `fc_token.desktop` into `~/.local/share/applications/` (or your chosen prefix)
- Icons into the standard `hicolor` theme locations.

---

## AppImage build

An `appimage-builder.yml` recipe is provided.

To build an AppImage:

```bash
appimage-builder --recipe appimage-builder.yml
```

This will:

- Create an AppDir.
- Build a Python virtualenv at `AppDir/usr/venv`.
- `pip install .` into that venv.
- Bundle Python/PyQt6 and required system libraries.
- Generate an AppImage that runs `fc-token` from the bundled venv.

When the build finishes, you should get something like:

```bash
./File_Centipede_Activation_Helper-x86_64.AppImage --version
./File_Centipede_Activation_Helper-x86_64.AppImage --self-test
```

You can then make it executable and run it directly:

```bash
chmod +x File_Centipede_Activation_Helper-x86_64.AppImage
./File_Centipede_Activation_Helper-x86_64.AppImage
```

---

## Usage

Once running:

- The main window shows the **current activation code** in a monospaced, soft-wrapped view.
- Use the **clipboard button** (or “Copy code” actions) to copy the current valid code.
- The **“Future codes…”** button opens a list of cached codes with their validity windows. Click a row to see the full code.
- The tray menu allows:

  - “Refresh now” plus a status submenu (last refresh, next run, timezone)
  - Opening the Settings dialog
  - Toggling daily auto-refresh
  - Changing tray icon theme (auto/light/dark)
  - Enabling/disabling desktop integration and autostart on login
  - Controlling whether the main window opens on start
  - Toggling status tooltip/menu visibility
  - Viewing the About dialog and quitting the application

Closing the main window will, by default, hide it to the tray. Use the tray menu to quit the application.

---

## CLI parameters

The `fc-token` launcher accepts a small set of flags:

```bash
# Print version and exit
fc-token --version
fc-token -V

# Run a lightweight self-test (no full GUI loop)
fc-token --self-test
```

---

## Development

The code is structured as a small, modular package:

- `fc_token.config` – configuration constants and metadata.
- `fc_token.models` – data models (`CodeEntry`, UTC helpers).
- `fc_token.scraper` – HTML scraping and parsing of activation codes.
- `fc_token.cache` – on-disk cache of codes with expiry filtering.
- `fc_token.icons` – icon/theme helpers and resource loading.
- `fc_token.ui.main_window` – main window UI.
- `fc_token.ui.tray` – system tray integration, scheduling, notifications.
- `fc_token.ui.dialogs.*` – “About”, “Future codes”, “Settings”, and timezone dialogs.
- `fc_token.ui.application` – Qt application bootstrap and `main()`.

To run from a checkout:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
fc-token --self-test
fc-token
```

---

## License & Credits

- This project is not affiliated with or endorsed by the File Centipede authors.
- Icons are duck-themed and packaged as part of this project.
- Ensure you have appropriate rights for any replacement artwork.
