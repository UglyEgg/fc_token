#!/usr/bin/env python3
"""
Installer for fc-token.

Installs or uninstalls the .desktop launcher and icons for either:

- user-local (default):   ~/.local/share
- system-wide:            /usr/local/share  (or another --prefix)

This assumes the Python package itself has already been installed so that
the 'fc-token' console script is on PATH, e.g.:

    uv tool install .
    # or
    pipx install .
    # or
    pip install .

Usage examples (from repo root):

    # Install for current user
    python installer.py install --user

    # Uninstall for current user
    python installer.py uninstall --user

    # Install system-wide (needs sudo)
    sudo python installer.py install --system

    # Install system-wide under /usr (instead of /usr/local)
    sudo python installer.py install --system --prefix /usr
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
RESOURCES_DIR = REPO_ROOT / "src" / "fc_token" / "resources"


def get_paths(system: bool, prefix: str | None) -> dict[str, Path]:
    if system:
        base_prefix = Path(prefix or "/usr/local")
        share = base_prefix / "share"
    else:
        data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        share = Path(data_home)

    apps_dir = share / "applications"
    icons_base = share / "icons" / "hicolor"

    return {
        "apps_dir": apps_dir,
        "icons_base": icons_base,
        "tray_symbolic_svg": icons_base / "scalable" / "apps" / "fc_token-symbolic.svg",
        "icon_256": icons_base / "256x256" / "apps" / "fc_token.png",
        "desktop": apps_dir / "fc_token.desktop",
        "share_root": share,
    }


def install(args: argparse.Namespace) -> int:
    paths = get_paths(system=args.system, prefix=args.prefix)

    apps_dir = paths["apps_dir"]
    icons_base = paths["icons_base"]
    tray_symbolic_svg = paths["tray_symbolic_svg"]
    icon_256 = paths["icon_256"]
    desktop_path = paths["desktop"]

    # Create directories
    (icons_base / "scalable" / "apps").mkdir(parents=True, exist_ok=True)
    (icons_base / "256x256" / "apps").mkdir(parents=True, exist_ok=True)
    apps_dir.mkdir(parents=True, exist_ok=True)

    # Copy icons from resources
    app_png = RESOURCES_DIR / "fc_token.png"
    tray_svg = RESOURCES_DIR / "fc_token_symbolic.svg"

    if app_png.exists():
        shutil.copyfile(app_png, icon_256)
        print(f"Installed app PNG icon -> {icon_256}")
    else:
        print("Warning: fc_token.png not found in resources/")

    if tray_svg.exists():
        shutil.copyfile(tray_svg, tray_symbolic_svg)
        print(f"Installed tray SVG icon -> {tray_symbolic_svg}")
    else:
        print("Warning: fc_token_symbolic.svg not found in resources/")

    # .desktop file
    desktop_content = """[Desktop Entry]
Type=Application
Name=File Centipede Activation Helper
GenericName=Activation Code Helper
Comment=Fetch and manage File Centipede activation codes
Exec=fc-token
Icon=fc_token
Terminal=false
Categories=Network;Qt;Utility;
StartupNotify=true
StartupWMClass=File Centipede Activation Codes
"""

    desktop_path.write_text(desktop_content, encoding="utf-8")
    print(f"Installed desktop file -> {desktop_path}")

    # Try to refresh desktop / icon databases (ignore failures)
    for cmd in (
        ["update-desktop-database", str(apps_dir)],
        ["gtk-update-icon-theme", str(paths["share_root"] / "icons")],
    ):
        try:
            subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    print(
        "\nDone. Make sure 'fc-token' is on your PATH "
        "(e.g. via 'uv tool install .' or 'pipx install .')."
    )
    return 0


def uninstall(args: argparse.Namespace) -> int:
    paths = get_paths(system=args.system, prefix=args.prefix)

    to_remove = [
        paths["desktop"],
        paths["tray_symbolic_svg"],
        paths["icon_256"],
    ]

    removed_any = False
    for p in to_remove:
        try:
            if p.exists():
                p.unlink()
                print(f"Removed {p}")
                removed_any = True
        except Exception as e:
            print(f"Warning: failed to remove {p}: {e}")

    if not removed_any:
        print("Nothing to remove; no installed launcher/icons found for this scope.")
    else:
        print("Uninstall completed for launcher/icons (Python package removal is separate).")

    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install or uninstall fc-token launcher and icons."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(p):
        scope = p.add_mutually_exclusive_group()
        scope.add_argument(
            "--user",
            action="store_true",
            default=False,
            help="Install/uninstall for current user (default).",
        )
        scope.add_argument(
            "--system",
            action="store_true",
            default=False,
            help="Install/uninstall system-wide (e.g. /usr/local/share). Requires sudo.",
        )
        p.add_argument(
            "--prefix",
            type=str,
            help="Custom prefix for system install (default: /usr/local). Only used with --system.",
        )

    p_install = subparsers.add_parser("install", help="Install launcher and icons.")
    add_common_flags(p_install)

    p_uninstall = subparsers.add_parser("uninstall", help="Uninstall launcher and icons.")
    add_common_flags(p_uninstall)

    args = parser.parse_args(argv)

    # default scope -> user
    if not args.user and not args.system:
        args.user = True

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if args.command == "install":
        return install(args)
    elif args.command == "uninstall":
        return uninstall(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
