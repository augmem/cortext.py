#!/usr/bin/env python3
"""Vendor cortext release assets into this package (turnkey ship path).

Downloads ``cortext-assets-<version>.tar.gz`` from augmem/cortext and installs
``native/`` + ``models/`` under ``cortext/`` so the wheel/sdist ships them.

Examples:
  python3 scripts/vendor_release_assets.py
  python3 scripts/vendor_release_assets.py --from-release v1.2.4 --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from cortext.assets import PACKAGE_DIR  # noqa: E402
from cortext.release import (  # noqa: E402
    DEFAULT_RELEASE_REPO,
    DEFAULT_RELEASE_TAG,
    download_release_assets,
    ensure_release_assets,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-release",
        default=DEFAULT_RELEASE_TAG,
        help=f"Release tag (default {DEFAULT_RELEASE_TAG}).",
    )
    parser.add_argument("--repo", default=DEFAULT_RELEASE_REPO)
    parser.add_argument(
        "--dest",
        type=Path,
        default=PACKAGE_DIR,
        help="Package directory to vendor into (default: cortext/).",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    dest = args.dest.expanduser().resolve()
    print(f"dest={dest}", flush=True)
    print(f"release={args.from_release} repo={args.repo}", flush=True)

    if args.force:
        path = download_release_assets(
            tag=args.from_release, dest=dest, repo=args.repo
        )
    else:
        path = ensure_release_assets(tag=args.from_release, dest=dest, force=False)

    print(
        f"\nVendored into package.\n"
        f"  native/ and models/ under {path}\n"
        f"  Commit these binaries for turnkey installs.\n",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
