"""Optional maintainer helpers to refresh shipped package assets from a release.

Runtime does **not** download. Assets ship inside ``cortext/native`` and
``cortext/models``. Use ``scripts/vendor_release_assets.py`` (or this module)
when cutting a new binding release.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .assets import PACKAGE_DIR, host_native_present, platform_tag

DEFAULT_RELEASE_TAG = os.environ.get("CORTEXT_RELEASE_TAG", "v1.3.0")
DEFAULT_RELEASE_REPO = os.environ.get("CORTEXT_RELEASE_REPO", "augmem/cortext.cpp")


def _http_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"cortext.py/{DEFAULT_RELEASE_TAG.lstrip('v')}",
            "Accept": "application/vnd.github+json",
        },
    )
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"cortext.py/{DEFAULT_RELEASE_TAG.lstrip('v')}"},
    )
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=600) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def _normalize_tag(tag: str | None) -> tuple[str, str]:
    raw = tag or DEFAULT_RELEASE_TAG
    if raw.upper() == "LATEST":
        raise RuntimeError("pin an exact release tag (e.g. v1.3.0); latest is not allowed")
    t = raw if raw.startswith("v") else f"v{raw}"
    return t, t.lstrip("v")


def _extract_tarball(tgz: Path, dest: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="cortext-assets-") as tmp:
        extract_root = Path(tmp) / "extracted"
        extract_root.mkdir()
        with tarfile.open(tgz, "r:gz") as tar:
            try:
                tar.extractall(extract_root, filter="data")
            except TypeError:
                tar.extractall(extract_root)
        if (extract_root / "native").is_dir():
            source = extract_root
        else:
            children = [p for p in extract_root.iterdir() if p.is_dir()]
            source = children[0] if len(children) == 1 else extract_root
        if not (source / "native").is_dir() or not (source / "models").is_dir():
            raise RuntimeError(f"release tarball missing native/ or models/: {tgz.name}")

        dest.mkdir(parents=True, exist_ok=True)
        for name in ("native", "models"):
            target = dest / name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source / name, target)
        top = source / "manifest.json"
        if top.is_file():
            shutil.copy2(top, dest / "assets-manifest.json")


def download_release_assets(
    *,
    tag: str | None = None,
    dest: Path | None = None,
    repo: str | None = None,
) -> Path:
    """Download release tarball into ``dest`` (default: package dir for vendoring)."""
    repo = repo or DEFAULT_RELEASE_REPO
    release_tag, version = _normalize_tag(tag)
    dest = (dest or PACKAGE_DIR).expanduser().resolve()

    asset_name = f"cortext-assets-{version}.tar.gz"
    api = f"https://api.github.com/repos/{repo}/releases/tags/{release_tag}"
    try:
        data = _http_json(api)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"could not fetch release {release_tag} from {repo}: HTTP {exc.code}"
        ) from exc

    assets = {a["name"]: a for a in data.get("assets") or []}
    if asset_name not in assets:
        names = ", ".join(sorted(assets)) or "(none)"
        raise RuntimeError(
            f"release {release_tag} has no {asset_name}. Available: {names}."
        )

    url = assets[asset_name]["browser_download_url"]
    with tempfile.TemporaryDirectory(prefix="cortext-dl-") as tmp:
        tgz = Path(tmp) / asset_name
        _download(url, tgz)
        sum_name = f"{asset_name}.sha256"
        if sum_name not in assets:
            raise RuntimeError(f"release {release_tag} missing {sum_name}")
        sum_path = Path(tmp) / sum_name
        _download(assets[sum_name]["browser_download_url"], sum_path)
        expected = sum_path.read_text(encoding="utf-8").split()[0].strip()
        h = hashlib.sha256()
        with tgz.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
        actual = h.hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"checksum mismatch for {asset_name}: got {actual} want {expected}"
            )
        _extract_tarball(tgz, dest)

    if not host_native_present(dest):
        raise RuntimeError(
            f"vendored assets at {dest} missing host native for {platform_tag()}"
        )
    if not (dest / "models" / "manifest.json").is_file():
        raise RuntimeError(f"vendored assets at {dest} missing models/manifest.json")
    return dest


def ensure_release_assets(
    *,
    tag: str | None = None,
    dest: Path | None = None,
    force: bool = False,
) -> Path:
    """Maintainer helper: ensure assets exist under package dir (or dest).

    Runtime loaders should use :func:`cortext.assets.assets_root` instead.
    """
    dest = (dest or PACKAGE_DIR).expanduser().resolve()
    if (
        not force
        and host_native_present(dest)
        and (dest / "models" / "manifest.json").is_file()
    ):
        return dest
    return download_release_assets(tag=tag or DEFAULT_RELEASE_TAG, dest=dest)
