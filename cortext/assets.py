"""Locate Cortext runtime assets shipped **inside this package**.

Turnkey layout (package data)::

    cortext/
      native/<platform-tag>/libcortext.* | cortext.dll
      models/manifest.json + AIST chunks + vocab

Resolution order:

1. ``CORTEXT_LIBRARY_PATH`` / ``CORTEXT_ASSETS_DIR`` — explicit overrides only
2. This package directory (``Path(__file__).parent``) — the shipped default

The PyPI wheel ships thin natives and downloads the verified model on first
use; the GitHub Release wheelhouse additionally ships model chunks.

No sibling trees or system library search are used by the asset locator.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path

SUPPORTED_NATIVE_TARGETS = frozenset(
    {
        "linux-aarch64",
        "linux-x86_64",
        "macos-aarch64",
        "macos-x86_64",
        "windows-aarch64",
        "windows-x86_64",
    }
)

PACKAGE_DIR = Path(__file__).resolve().parent


def platform_tag() -> str:
    system = platform.system().lower()
    if system == "darwin":
        os_tag = "macos"
    elif system == "linux":
        os_tag = "linux"
    elif system == "windows":
        os_tag = "windows"
    else:
        os_tag = system or "unknown"

    machine = platform.machine().lower()
    if machine in {"amd64", "x64"}:
        arch = "x86_64"
    elif machine == "arm64":
        arch = "aarch64"
    else:
        arch = machine or "unknown"

    return f"{os_tag}-{arch}"


def library_name_for_tag(tag: str) -> str:
    os_tag = tag.split("-", 1)[0]
    if os_tag == "macos":
        return "libcortext.dylib"
    if os_tag == "windows":
        return "cortext.dll"
    return "libcortext.so"


def host_library_path(root: Path) -> Path:
    tag = platform_tag()
    if tag not in SUPPORTED_NATIVE_TARGETS:
        raise RuntimeError(
            f"unsupported platform tag {tag!r}; shipped tags: "
            + ", ".join(sorted(SUPPORTED_NATIVE_TARGETS))
        )
    return root / "native" / tag / library_name_for_tag(tag)


def host_native_present(root: Path) -> bool:
    try:
        return host_library_path(root).is_file()
    except RuntimeError:
        return False


def package_assets_ready() -> bool:
    """True when this install includes the host native + model manifest."""
    return host_native_present(PACKAGE_DIR) and (
        PACKAGE_DIR / "models" / "manifest.json"
    ).is_file()


def assets_root() -> Path:
    """Return the assets root (override or shipped package). Fails hard if missing."""
    env = os.environ.get("CORTEXT_ASSETS_DIR")
    if env:
        path = Path(env).expanduser().resolve()
        if not host_native_present(path):
            raise RuntimeError(
                f"CORTEXT_ASSETS_DIR={path} missing host native for {platform_tag()}"
            )
        return path

    if host_native_present(PACKAGE_DIR):
        return PACKAGE_DIR

    raise RuntimeError(
        "cortext package is missing the host native under "
        f"{PACKAGE_DIR}/native. Rebuild with scripts/vendor_release_assets.py "
        "or set CORTEXT_ASSETS_DIR."
    )


def models_root() -> Path:
    env = os.environ.get("CORTEXT_ASSETS_DIR")
    root = Path(env).expanduser().resolve() if env else PACKAGE_DIR
    models = root / "models"
    if not (models / "manifest.json").is_file():
        raise RuntimeError(f"models/manifest.json missing under assets root {root}")
    return models


def candidate_library_paths() -> list[Path]:
    """Explicit library path, then shipped (or override) host native only."""
    candidates: list[Path] = []

    env_path = os.environ.get("CORTEXT_LIBRARY_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    # Prefer override assets root, else package.
    roots: list[Path] = []
    env_assets = os.environ.get("CORTEXT_ASSETS_DIR")
    if env_assets:
        roots.append(Path(env_assets).expanduser().resolve())
    roots.append(PACKAGE_DIR)

    seen: set[Path] = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        try:
            candidates.append(host_library_path(root))
        except RuntimeError:
            continue

    return candidates
