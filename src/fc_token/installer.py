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

Usage examples:

    # Install launcher/icons for current user
    python -m fc_token.installer install --user

    # Install launcher/icons system-wide (requires sudo)
    sudo python -m fc_token.installer install --system

    # Uninstall from user-local location
    python -m fc_token.installer uninstall --user
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from fc_token.config import DESKTOP_FILENAME
from fc_token.desktop_entry import build_launcher_desktop


ICON_PNG_NAME = "fc_token.png"
ICON_SYMBOLIC_NAME = "fc_token_symbolic.svg"


@dataclass(frozen=True, slots=True)
class InstallTarget:
    """Target base for installing desktop file and icons."""

    prefix: Path  # e.g. ~/.local/share or /usr/local/share

    @property
    def applications_dir(self) -> Path:
        return self.prefix / "applications"

    @property
    def icons_dir(self) -> Path:
        return self.prefix / "icons" / "hicolor"

    @property
    def png_target(self) -> Path:
        # 256x256 pixel icon
        return self.icons_dir / "256x256" / "apps" / "fc_token.png"

    @property
    def symbolic_target(self) -> Path:
        # Scalable symbolic icon
        return self.icons_dir / "scalable" / "apps" / "fc_token-symbolic.svg"

    @property
    def desktop_target(self) -> Path:
        return self.applications_dir / DESKTOP_FILENAME


def find_resource(name: str) -> Path:
    """Return a path to a resource file packaged with fc_token."""
    try:
        pkg_root = files("fc_token.resources")
        candidate = pkg_root.joinpath(name)
        if candidate.is_file():
            return Path(candidate)
    except Exception as exc:  # pragma: no cover - very unlikely
        raise FileNotFoundError(f"Could not locate resource {name}: {exc}") from exc
    raise FileNotFoundError(f"Resource not found: {name}")


def write_text_file(path: Path, content: str) -> None:
    """Write UTF-8 text to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_file(src: Path, dst: Path) -> None:
    """Copy a file into place, creating parent directories as needed."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def install_launcher(target: InstallTarget) -> None:
    """Install the .desktop file and icons into the given target."""
    print(f"[fc-token] Installing desktop file into {target.applications_dir}")
    write_text_file(target.desktop_target, build_launcher_desktop())

    print(f"[fc-token] Installing icons into {target.icons_dir}")
    png_src = find_resource(ICON_PNG_NAME)
    svg_src = find_resource(ICON_SYMBOLIC_NAME)

    copy_file(png_src, target.png_target)
    copy_file(svg_src, target.symbolic_target)

    print("[fc-token] Installation complete.")


def uninstall_launcher(target: InstallTarget) -> None:
    """Remove the .desktop file and icons from the given target."""
    removed_any = False
    for path in [
        target.desktop_target,
        target.png_target,
        target.symbolic_target,
    ]:
        if path.exists():
            print(f"[fc-token] Removing {path}")
            try:
                path.unlink()
                removed_any = True
            except Exception as exc:
                print(f"[fc-token] Failed to remove {path}: {exc}", file=sys.stderr)

    if not removed_any:
        print("[fc-token] Nothing to remove for this target.")
    else:
        print("[fc-token] Uninstall complete for this target.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for the installer."""
    parser = argparse.ArgumentParser(
        description="Install or uninstall the fc-token desktop launcher and icons."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_install_args(p: argparse.ArgumentParser) -> None:
        scope = p.add_mutually_exclusive_group()
        scope.add_argument(
            "--user",
            action="store_true",
            help="Install into the current user's ~/.local/share (default).",
        )
        scope.add_argument(
            "--system",
            action="store_true",
            help="Install into a system prefix (requires appropriate permissions).",
        )
        p.add_argument(
            "--prefix",
            type=str,
            default="/usr/local/share",
            help="Base prefix for system-wide installation (default: /usr/local/share). "
            "Ignored when --user is given.",
        )

    install_parser = subparsers.add_parser(
        "install", help="Install launcher and icons."
    )
    add_common_install_args(install_parser)

    uninstall_parser = subparsers.add_parser(
        "uninstall", help="Uninstall launcher and icons."
    )
    add_common_install_args(uninstall_parser)

    return parser.parse_args(argv)


def target_from_args(args: argparse.Namespace) -> InstallTarget:
    """Create an InstallTarget from parsed arguments."""
    if args.user or not args.system:
        # Default: user-local
        base = (
            Path(os.environ.get("XDG_DATA_HOME", ""))
            or Path.home() / ".local" / "share"
        )
        return InstallTarget(prefix=base)

    # System-wide install
    base = Path(args.prefix)
    return InstallTarget(prefix=base)


def main(argv: list[str] | None = None) -> int:
    """Run the installer CLI."""
    args = parse_args(argv or sys.argv[1:])
    target = target_from_args(args)

    if args.command == "install":
        install_launcher(target)
        return 0
    if args.command == "uninstall":
        uninstall_launcher(target)
        return 0

    # pragma: no cover - argparse enforces choices
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
