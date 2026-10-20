#!/usr/bin/env python3
"""Write pip-compatible wheel indexes for a GitHub Release wheelhouse.

Produces:
  index.html              — flat find-links page (pip --find-links URL)
  simple/index.html       — PEP 503 root
  simple/augmem-cortext/index.html — PEP 503 project page

When --base-url is set, all links are absolute (required for GitHub Releases
assets, since the index is itself a release asset).

Examples:
  python3 scripts/write_wheel_index.py dist/wheels --version 2.0.0
  python3 scripts/write_wheel_index.py dist/wheels \\
    --version 2.0.0 \\
    --base-url https://github.com/augmem/cortext.py/releases/download/v2.0.0
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def project_version_from_pyproject(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not m:
        raise SystemExit("could not parse version from pyproject.toml")
    return m.group(1)


def href(name: str, base_url: str | None) -> str:
    if not base_url:
        return name
    return f"{base_url.rstrip('/')}/{name}"


def write_find_links(out_dir: Path, wheels: list[Path], version: str, base_url: str | None) -> None:
    lines = [
        "<!DOCTYPE html>",
        f"<html><head><meta charset='utf-8'><title>cortext {version} wheels</title></head><body>",
        f"<h1>cortext {version} platform wheels</h1>",
        "<p>Install (pip selects the wheel for your platform):</p>",
        "<pre>",
    ]
    if base_url:
        index = f"{base_url.rstrip('/')}/index.html"
        lines.append(f"pip install augmem.cortext=={version} --find-links {index}")
        lines.append(f"uv pip install augmem.cortext=={version} --find-links {index}")
    else:
        lines.append(f"pip install augmem.cortext=={version} --find-links {out_dir} --no-index")
    lines.extend(["</pre>", "<ul>"])
    for whl in wheels:
        lines.append(f'  <li><a href="{href(whl.name, base_url)}">{whl.name}</a></li>')
    lines.extend(["</ul>", "</body></html>", ""])
    (out_dir / "index.html").write_text("\n".join(lines), encoding="utf-8")


def write_pep503(out_dir: Path, wheels: list[Path], version: str, base_url: str | None) -> None:
    """Write a minimal simple repository under out_dir/simple/."""
    simple = out_dir / "simple"
    project = simple / "augmem-cortext"
    project.mkdir(parents=True, exist_ok=True)

    # Root simple index
    (simple / "index.html").write_text(
        "\n".join(
            [
                "<!DOCTYPE html>",
                "<html><head><meta charset='utf-8'><title>simple</title></head><body>",
                '<a href="augmem-cortext/">augmem.cortext</a>',
                "</body></html>",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Project page — pip uses this with --index-url .../simple
    lines = [
        "<!DOCTYPE html>",
        f"<html><head><meta charset='utf-8'><title>cortext {version}</title></head><body>",
        f"<h1>cortext {version}</h1>",
    ]
    for whl in wheels:
        # PEP 503: filename in the link text; optional data-requires-python
        lines.append(
            f'<a href="{href(whl.name, base_url)}" data-requires-python="&gt;=3.10">'
            f"{whl.name}</a><br/>"
        )
    lines.extend(["</body></html>", ""])
    (project / "index.html").write_text("\n".join(lines), encoding="utf-8")


def write_install_snippet(out_dir: Path, version: str, base_url: str | None, repo: str) -> None:
    tag = f"v{version}"
    if not base_url:
        base_url = f"https://github.com/{repo}/releases/download/{tag}"
    index = f"{base_url.rstrip('/')}/index.html"
    simple = f"{base_url.rstrip('/')}/simple"
    text = f"""# Install cortext {version} (GitHub Releases wheelhouse)

Platform wheels are hosted on this release (not pypi.org), same idea as PyTorch's
secondary index.

## Install (find-links)

```bash
pip install augmem.cortext=={version} --find-links {index}
# or
uv pip install augmem.cortext=={version} --find-links {index}
```

Pip/uv picks the matching `py3-none-<platform>` wheel for your OS/arch.

## Helper script

```bash
curl -fsSL {base_url.rstrip('/')}/install.sh | bash -s -- {tag}
# or from a checkout:
./scripts/install_from_release.sh {tag}
```

## Mirrors

This release also has `simple-index.tar.gz` (PEP 503 layout). Unpack and host
the `simple/` directory on any static file server if you need `--index-url`.
"""
    (out_dir / "INSTALL.md").write_text(text, encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels_dir", type=Path, help="Directory containing *.whl files")
    parser.add_argument("--version", default=None, help="Package version (default: pyproject)")
    parser.add_argument(
        "--base-url",
        default=None,
        help="Absolute base URL for wheel links (GitHub release download prefix).",
    )
    parser.add_argument(
        "--repo",
        default="augmem/cortext.py",
        help="GitHub owner/repo for install docs (default augmem/cortext.py).",
    )
    args = parser.parse_args()

    out_dir = args.wheels_dir.expanduser().resolve()
    version = args.version or project_version_from_pyproject(root)
    wheels = sorted(out_dir.glob("*.whl"))
    if not wheels:
        raise SystemExit(f"no wheels in {out_dir}")

    write_find_links(out_dir, wheels, version, args.base_url)
    write_pep503(out_dir, wheels, version, args.base_url)
    write_install_snippet(out_dir, version, args.base_url, args.repo)
    print(f"wrote indexes for {len(wheels)} wheels → {out_dir}", flush=True)
    if args.base_url:
        print(f"  find-links: {args.base_url.rstrip('/')}/index.html", flush=True)
        print(f"  simple:     {args.base_url.rstrip('/')}/simple", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
