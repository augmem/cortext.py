#!/usr/bin/env python3
"""Build per-architecture turnkey wheels (PyTorch-style platform tags).

Each wheel contains:
  - pure Python binding sources
  - models/ (AIST chunks + vocab + manifest)
  - only native/<package-tag>/ for that platform

Wheel tags (py3-none-<plat>):

  linux-x86_64    → manylinux_2_17_x86_64.manylinux2014_x86_64
  linux-aarch64   → manylinux_2_17_aarch64.manylinux2014_aarch64
  macos-x86_64    → macosx_11_0_x86_64
  macos-aarch64   → macosx_11_0_arm64
  windows-x86_64  → win_amd64
  windows-aarch64 → win_arm64

Examples:
  python3 scripts/build_wheels.py
  python3 scripts/build_wheels.py --target macos-aarch64
  python3 scripts/build_wheels.py --out dist/wheels
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "cortext"
DEFAULT_OUT = ROOT / "dist" / "wheels"

# package_tag → (artifact name, PEP 427 platform tag)
TARGETS: dict[str, tuple[str, str]] = {
    "linux-x86_64": (
        "libcortext.so",
        "manylinux_2_17_x86_64.manylinux2014_x86_64",
    ),
    "linux-aarch64": (
        "libcortext.so",
        "manylinux_2_17_aarch64.manylinux2014_aarch64",
    ),
    "macos-x86_64": (
        "libcortext.dylib",
        "macosx_11_0_x86_64",
    ),
    "macos-aarch64": (
        "libcortext.dylib",
        "macosx_11_0_arm64",
    ),
    "windows-x86_64": (
        "cortext.dll",
        "win_amd64",
    ),
    "windows-aarch64": (
        "cortext.dll",
        "win_arm64",
    ),
}


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd or ROOT, check=True)


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not m:
        raise SystemExit("could not parse version from pyproject.toml")
    return m.group(1)


def require_native(tag: str, artifact: str) -> Path:
    path = PACKAGE / "native" / tag / artifact
    if not path.is_file():
        raise SystemExit(
            f"missing native for {tag}: {path}\n"
            "Run: python3 scripts/vendor_release_assets.py --from-release v2.0.0"
        )
    return path


def stage_tree(staging: Path, tag: str, artifact: str) -> None:
    """Copy package sources + models + single-platform native into staging."""
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    # Project metadata
    for name in ("pyproject.toml", "README.md", "LICENSE", "MANIFEST.in", ".gitattributes"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, staging / name)

    # Python package without multi-arch natives
    pkg_dst = staging / "cortext"
    pkg_dst.mkdir()
    for path in PACKAGE.iterdir():
        if path.name in {"native", "models", "__pycache__"}:
            continue
        if path.suffix == ".pyc":
            continue
        if path.is_file():
            shutil.copy2(path, pkg_dst / path.name)
        elif path.is_dir() and path.name not in {"native", "models"}:
            shutil.copytree(
                path,
                pkg_dst / path.name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

    # Models (full — turnkey)
    models_src = PACKAGE / "models"
    if not (models_src / "manifest.json").is_file():
        raise SystemExit(f"missing models under {models_src}")
    shutil.copytree(
        models_src,
        pkg_dst / "models",
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    # Single native
    native_src = require_native(tag, artifact)
    native_dst = pkg_dst / "native" / tag
    native_dst.mkdir(parents=True)
    shutil.copy2(native_src, native_dst / artifact)

    # Slim native manifest for this wheel only
    import json

    native_manifest = {
        "schema": "augmem.cortext.native.v1",
        "optimize": "ReleaseSmall",
        "wheel_package_tag": tag,
        "targets": [
            {
                "package_tag": tag,
                "artifact": artifact,
                "size": native_src.stat().st_size,
            }
        ],
    }
    (pkg_dst / "native" / "manifest.json").write_text(
        json.dumps(native_manifest, indent=2) + "\n", encoding="utf-8"
    )

    # Restrict package-data in staged pyproject to this layout (already only one native)
    # Ensure package-data still includes native/** and models/**
    pyproject = (staging / "pyproject.toml").read_text(encoding="utf-8")
    if "native/**/*" not in pyproject:
        raise SystemExit("staged pyproject missing native package-data")


def build_one(tag: str, plat_tag: str, artifact: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"cortext-wheel-{tag}-") as tmp:
        staging = Path(tmp) / "src"
        stage_tree(staging, tag, artifact)

        # Build a pure wheel then retag to platform-specific (py3-none-<plat>).
        build_out = Path(tmp) / "dist"
        build_out.mkdir()
        run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--outdir",
                str(build_out),
                str(staging),
            ]
        )
        wheels = list(build_out.glob("*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected one wheel in {build_out}, got {wheels}")
        any_wheel = wheels[0]

        # Retag py3-none-any → py3-none-<platform>
        # wheel tags rewrites filename in place when --remove is passed.
        run(
            [
                sys.executable,
                "-m",
                "wheel",
                "tags",
                "--python-tag",
                "py3",
                "--abi-tag",
                "none",
                "--platform-tag",
                plat_tag,
                "--remove",
                str(any_wheel),
            ]
        )
        tagged = list(build_out.glob("*.whl"))
        if len(tagged) != 1:
            raise SystemExit(f"retag failed in {build_out}: {tagged}")
        final = out_dir / tagged[0].name
        if final.exists():
            final.unlink()
        shutil.move(str(tagged[0]), str(final))
        size_mib = final.stat().st_size / (1024 * 1024)
        print(f"built {final.name} ({size_mib:.1f} MiB) for {tag}", flush=True)
        return final


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--target",
        action="append",
        default=[],
        help="Package tag (e.g. macos-aarch64). Repeatable. Default: all present.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default {DEFAULT_OUT}).",
    )
    p.add_argument(
        "--base-url",
        default=None,
        help="If set, write indexes with absolute wheel URLs (GitHub Release prefix).",
    )
    p.add_argument(
        "--repo",
        default="augmem/cortext.py",
        help="GitHub owner/repo for install docs (default augmem/cortext.py).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    version = project_version()
    out_dir = args.out.expanduser().resolve()

    if args.target:
        selected = args.target
        for t in selected:
            if t not in TARGETS:
                raise SystemExit(f"unknown target {t!r}; choose from {', '.join(TARGETS)}")
    else:
        selected = [
            tag
            for tag, (artifact, _) in TARGETS.items()
            if (PACKAGE / "native" / tag / artifact).is_file()
        ]
        if not selected:
            raise SystemExit("no natives found under cortext/native/; vendor assets first")

    print(f"version={version}", flush=True)
    print(f"targets={selected}", flush=True)
    print(f"out={out_dir}", flush=True)

    wheels: list[Path] = []
    for tag in selected:
        artifact, plat_tag = TARGETS[tag]
        wheels.append(build_one(tag, plat_tag, artifact, out_dir))

    # Local relative index + optional absolute GitHub Release index
    index_script = ROOT / "scripts" / "write_wheel_index.py"
    cmd = [sys.executable, str(index_script), str(out_dir), "--version", version, "--repo", args.repo]
    if args.base_url:
        cmd.extend(["--base-url", args.base_url])
    run(cmd)

    print("\nInstall (current machine picks matching wheel):", flush=True)
    if args.base_url:
        idx = f"{args.base_url.rstrip('/')}/index.html"
        print(f"  pip install augmem.cortext=={version} --find-links {idx}", flush=True)
        print(f"  uv pip install augmem.cortext=={version} --find-links {idx}", flush=True)
    else:
        print(f"  pip install augmem.cortext=={version} --find-links {out_dir} --no-index", flush=True)
        print(f"  uv pip install augmem.cortext=={version} --find-links {out_dir}", flush=True)
        print(
            "  # GitHub Releases (after publish):\n"
            f"  ./scripts/install_from_release.sh v{version}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
