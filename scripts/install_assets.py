#!/usr/bin/env python3
"""Alias for maintainer vendoring — see vendor_release_assets.py.

Runtime installs are turnkey: natives and models ship inside the package.
This script only refreshes those package assets from a cortext GitHub Release.
"""
from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).with_name("vendor_release_assets.py")),
        run_name="__main__",
    )
