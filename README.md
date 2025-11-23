# fc-token

**fc-token** is a small KDE/Plasma-friendly tray utility that keeps your File Centipede
trial activation codes up to date. It runs in the system tray, periodically scrapes
the official activation page, and lets you quickly copy the current valid code.

---

## Features

- 🖥️ **KDE/Plasma 6–friendly tray application**
  - Close to tray, quit from tray menu.
  - Uses your duck-themed icons for both window and tray.
- 🔁 **Automatic refresh**
  - Configurable refresh interval (in minutes).
  - Manual “Refresh now” button and tray action.
- 🔑 **Current activation code at a glance**
  - Shows the active code and all cached codes with their validity ranges.
  - One-click “Copy current code to clipboard” button.
- 🔔 **Code-change notification**
  - When the active code changes, a desktop notification is shown.
  - The tray icon gets a small red-dot badge until you acknowledge it.
- 🎨 **Tray icon theming (Auto / Light / Dark)**
  - Auto mode tries to detect whether your theme is dark or light and chooses
    a matching tray icon style.
  - Override to Light or Dark for maximum contrast in your panel.
- 🧩 **Self-installing launcher + icons (per-user)**
  - Use the provided `installer.py` script to install the launcher and icons.tall or remove the `.desktop` launcher and icons
    into your user’s XDG data directories.
  - Integrates with the KDE application launcher and icon theme.

---

## Project layout

This project uses a modern `src/` layout and is designed to play nicely with
[uv](https://github.com/astral-sh/uv) and `setuptools`:

```text
fc_token_full_project/
├─ pyproject.toml
├─ README.md
├─ docs/
│  ├─ screenshot-main.png
│  └─ screenshot-tray-menu.png
└─ src/
   └─ fc_token/
      ├─ __init__.py
      ├─ app.py
      └─ resources/
         ├─ fc_token.svg
         └─ fc_token_symbolic.png
```

- `app.py` contains the main application code and `main()` entry point.
- Icons live under `src/fc_token/resources/` and are also bundled as package data.

---

## Screenshots

> The screenshots below are simple placeholders; replace `docs/*.png` with your own
> real screenshots if you like.

### Main window

![Main window](docs/screenshot-main.png)

### Tray menu and notifications

![Tray menu](docs/screenshot-tray-menu.png)

---

## Installation & usage

### 1. Requirements

- Python **3.13** or newer.
- A recent Linux desktop (KDE Plasma 6 recommended).
- `uv` (for development) or `pip` (for normal installation).

### 2. Clone and sync with uv

From the project root:

```bash
uv sync
```

This will create a virtual environment, install dependencies, and prepare the
`fc-token` entry point.

### 3. Running the app (development)

From the project root:

```bash
uv run fc-token
```

This launches the app, shows the main window, and adds a tray icon.

### 4. Installing a user-level CLI

If you want a globally available `fc-token` command in your user environment:

```bash
uv tool install .
```

Now you can simply run:

```bash
fc-token
```

from anywhere.

> **Note:** The `.desktop` launcher created by the app expects the `fc-token`
> command to be on your `PATH`. Using `uv tool install .` or a standard `pip install`
> satisfies this.

---

## KDE integration

### Installing launcher & icons (via installer.py)

Open the tray icon’s context menu and choose:

- **“Install launcher & icons”**

This will:

- Install `fc_token.desktop` to:  
  `~/.local/share/applications/fc_token.desktop`
- Install icons to:  
  - `~/.local/share/icons/hicolor/scalable/apps/fc_token.svg`  
  - `~/.local/share/icons/hicolor/24x24/apps/fc_token-symbolic.png`

It also tries to refresh the desktop and icon databases so that the new launcher
shows up in the KDE Application Launcher.

### Removing launcher & icons

From the same tray menu, choose:

- **“Remove launcher & icons”**

This removes the `.desktop` file and the icons that were installed for the current user.

### Autostart (optional)

Once the launcher is installed, you can add the app to KDE’s autostart via:

1. **System Settings → Startup and Shutdown → Autostart**
2. Click **“Add Application…”**
3. Choose **“File Centipede Activation Helper”** (the name from `fc_token.desktop`).

---

## Tray icon theming (Auto / Light / Dark)

The tray icon comes in a single base (monochrome) design which is recolored at runtime:

- **Auto** (default): detects whether the current Qt theme is dark or light and
  chooses a light or dark tray icon accordingly.
- **Light**: forces a light tray icon (better on dark panels).
- **Dark**: forces a dark tray icon (better on light panels).

You can switch modes via:

> Tray icon → **Tray icon theme** → Auto / Light / Dark

The small red-dot “badge” is applied on top of whichever variant is active whenever
a new, unseen activation code is detected.

---

## Configuration & data

- Settings are stored via `QSettings` under the `fc_token` organization and app name.
  They include:
  - Refresh interval
  - Auto-refresh enabled/disabled
  - Tray icon mode (Auto / Light / Dark)
- Cached activation codes are stored in an XDG cache directory, typically under:  
  `~/.cache/fc_token/file_centipede_codes.json`

---

## Development tips

- If you modify `app.py` or the resources while developing, just run:

  ```bash
  uv run fc-token
  ```

  again; no rebuild step is necessary for local testing.

- To rebuild the editable installation (if needed):

  ```bash
  uv sync
  ```

- To uninstall the tool installed via `uv tool install .`:

  ```bash
  uv tool uninstall fc-token
  ```

---

## License & credits

- This project wraps the File Centipede activation mechanism with a local helper
  tool but is **not** affiliated with or endorsed by the File Centipede authors.
- Icons are duck-themed and packaged as part of this project. If you swap them
  out for other artwork, please ensure you have the rights to use and distribute it.
