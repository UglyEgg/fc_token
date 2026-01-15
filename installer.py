#!/usr/bin/env python3
"""Compatibility wrapper for running the installer via this script."""

from __future__ import annotations

from fc_token.installer import main


if __name__ == "__main__":
    raise SystemExit(main())
