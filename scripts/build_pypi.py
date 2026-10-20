#!/usr/bin/env python3
"""Build the slim ``augmem.cortext`` PyPI distribution.

PyPI wheels contain all six thin v1.3 native libraries and the verified model
bootstrap code, but omit the 141 MB model chunks that make the turnkey GitHub
Release wheels exceed PyPI's per-file limit.

Example::

    python3 scripts/build_pypi.py \\
      --native-root /tmp/cortext-thin-v1.3-build
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "cortext"

TARGETS: dict[str, str] = {
    "linux-x86_64": "libcortext.so",
    "linux-aarch64": "libcortext.so",
    "macos-x86_64": "libcortext.dylib",
    "macos-aarch64": "libcortext.dylib",
    "windows-x86_64": "cortext.dll",
    "windows-aarch64": "cortext.dll",
}


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("could not parse version from pyproject.toml")
    return match.group(1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_python_package(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.name in {"native", "models", "__pycache__"}:
            continue
        if path.suffix == ".pyc":
            continue
        target = destination / path.name
        if path.is_dir():
            shutil.copytree(
                path,
                target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        else:
            shutil.copy2(path, target)


def stage_tree(staging: Path, native_root: Path, version: str) -> list[Path]:
    staging.mkdir(parents=True, exist_ok=True)
    for name in ("pyproject.toml", "README.md", "LICENSE", "MANIFEST.in", ".gitattributes"):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, staging / name)

    copy_python_package(PACKAGE, staging / "cortext")
    copy_python_package(ROOT / "augmem", staging / "augmem")

    native_destination = staging / "cortext" / "native"
    native_destination.mkdir(parents=True)
    manifest_targets: list[dict[str, object]] = []
    for tag, artifact in TARGETS.items():
        source = native_root / tag / "lib" / artifact
        if artifact == "cortext.dll":
            source = native_root / tag / "bin" / artifact
        if not source.is_file():
            raise SystemExit(f"missing thin native for {tag}: {source}")
        destination = native_destination / tag
        destination.mkdir(parents=True)
        target = destination / artifact
        shutil.copy2(source, target)
        manifest_targets.append(
            {
                "package_tag": tag,
                "artifact": artifact,
                "size": target.stat().st_size,
                "sha256": sha256_file(target),
            }
        )

    (native_destination / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "augmem.cortext.native.v1",
                "cortext_version": version,
                "optimize": "ReleaseSmall",
                "embedded_model": False,
                "targets": manifest_targets,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (staging / "cortext" / "assets-manifest.json").write_text(
        json.dumps(
            {
                "schema": "augmem.cortext.pypi_assets.v1",
                "cortext_version": version,
                "native": {"embedded_model": False, "targets": manifest_targets},
                "model": {
                    "source": "https://huggingface.co/augmem/AIST-87M-GGUF",
                    "download": "first engine creation",
                    "verification": "pinned sha256 and size",
                },
                "li_model": {
                    "source": "https://github.com/augmem/cortext.cpp/blob/f0b681e97450a4955458d0f4b140f58d15bba650/models/AIST-87M-GGUF/chunks/AIST-87M-LI.gguf.part-000",
                    "download": "first engine creation, beside the AIST model",
                    "verification": "pinned sha256 and size",
                    "override": "CORTEXT_LI_MODEL_PATH",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return [native_destination / tag / artifact for tag, artifact in TARGETS.items()]


def build(native_root: Path, out_dir: Path) -> list[Path]:
    version = project_version()
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="augmem-cortext-pypi-") as temp:
        staging = Path(temp) / "source"
        stage_tree(staging, native_root, version)
        if importlib.util.find_spec("build") is not None:
            command = [sys.executable, "-m", "build"]
            output_flag = "--outdir"
        elif shutil.which("uv"):
            command = ["uv", "build"]
            output_flag = "--out-dir"
        else:
            raise SystemExit("install build or uv to create PyPI artifacts")
        subprocess.run(
            command
            + [
                "--wheel",
                "--sdist",
                output_flag,
                str(out_dir),
                str(staging),
            ],
            check=True,
        )
    artifacts = sorted(out_dir.glob(f"*{version}*"))
    if not artifacts:
        raise SystemExit(f"no {version} artifacts written to {out_dir}")
    for artifact in artifacts:
        size_mib = artifact.stat().st_size / (1024 * 1024)
        print(f"built {artifact.name} ({size_mib:.1f} MiB)", flush=True)
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--native-root",
        type=Path,
        required=True,
        help="Root containing <platform>/lib or <platform>/bin thin natives.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "dist" / "pypi",
        help="Artifact directory (default: dist/pypi).",
    )
    args = parser.parse_args()
    build(args.native_root.expanduser().resolve(), args.out.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
