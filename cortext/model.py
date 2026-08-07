"""AIST model materialize from **shipped** package model chunks.

Chunks live under ``cortext/models/`` (package data). No network or sibling search.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .assets import models_root as _assets_models_root

MODEL_ASSET_NAME = "AIST-87M-GGUF/AIST-87M_q8_0.gguf"
VOCAB_ASSET_NAME = "mdbr-leaf-ir/vocab.txt"

_materialize_lock = threading.Lock()
_materialized_cache: dict[str, str] = {}

_AIST_MODEL_URL = (
    "https://huggingface.co/augmem/AIST-87M-GGUF/resolve/main/"
    "AIST-87M_q8_0.gguf?download=1"
)
_AIST_MODEL_SHA256 = "bf4c49954eccc65183f1a97e44606e86c7ee5a4fea500457124b687a3ec97898"
_AIST_MODEL_SIZE = 141491936
_VOCAB_URL = (
    "https://huggingface.co/bert-base-uncased/resolve/main/vocab.txt?download=1"
)
_VOCAB_SHA256 = "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3"
_VOCAB_SIZE = 231508
_DOWNLOAD_TIMEOUT_SECONDS = 60


def models_root() -> Path:
    return _assets_models_root()


def chunks_ready(root: Path | None = None) -> bool:
    try:
        models = root if root is not None else models_root()
    except RuntimeError:
        return False
    manifest = models / "manifest.json"
    if not manifest.is_file():
        return False
    chunk0 = models / "AIST-87M-GGUF" / "chunks" / "AIST-87M_q8_0.gguf.part-000"
    return chunk0.is_file()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_has_sha256(path: Path, want: str) -> tuple[bool, str]:
    if not path.is_file():
        return False, ""
    got = sha256_file(path)
    return got == want, got


def model_cache_dir(db_path: str = ":memory:") -> Path:
    """Where reassembled full GGUF files land (not the release asset store).

    1. ``CORTEXT_MODEL_CACHE_DIR``
    2. ``<dir(dbPath)>/.cortext-assets`` (``:memory:`` → process cwd)
    3. OS user cache under ``augmem/cortext/models``
    """
    override = os.environ.get("CORTEXT_MODEL_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if db_path and db_path != ":memory:":
        try:
            return Path(db_path).expanduser().resolve().parent / ".cortext-assets"
        except OSError:
            pass

    try:
        return Path.cwd() / ".cortext-assets"
    except OSError:
        pass

    return default_user_model_cache()


def default_user_model_cache() -> Path:
    system = platform.system().lower()
    home = Path.home()
    if system == "darwin":
        return home / "Library" / "Caches" / "augmem" / "cortext" / "models"
    if system == "windows":
        base = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base).expanduser() / "augmem" / "cortext" / "models"
    base = os.environ.get("XDG_CACHE_HOME") or str(home / ".cache")
    return Path(base).expanduser() / "augmem" / "cortext" / "models"


def _verified_file(path: Path, sha256: str, size: int) -> bool:
    return path.is_file() and path.stat().st_size == size and sha256_file(path) == sha256


def _download_verified(url: str, dest: Path, sha256: str, size: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "augmem.cortext/1.3.0 model bootstrap"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
            with tmp.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
        if not _verified_file(tmp, sha256, size):
            actual_size = tmp.stat().st_size
            actual_sha256 = sha256_file(tmp)
            raise RuntimeError(
                f"downloaded {dest.name} failed verification: "
                f"size={actual_size} sha256={actual_sha256}"
            )
        tmp.replace(dest)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"could not download Cortext model asset {dest.name}: HTTP {exc.code}. "
            "Set CORTEXT_AIST_MODEL_PATH to an existing AIST GGUF file or retry later."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"could not download Cortext model asset {dest.name}: {exc.reason}. "
            "Set CORTEXT_AIST_MODEL_PATH to an existing AIST GGUF file or retry later."
        ) from exc
    finally:
        tmp.unlink(missing_ok=True)


def _remote_model_path(cache_dir: Path) -> str:
    model_path = cache_dir / "AIST-87M-GGUF" / "AIST-87M_q8_0.gguf"
    vocab_path = cache_dir / "mdbr-leaf-ir" / "vocab.txt"
    if not _verified_file(model_path, _AIST_MODEL_SHA256, _AIST_MODEL_SIZE):
        _download_verified(_AIST_MODEL_URL, model_path, _AIST_MODEL_SHA256, _AIST_MODEL_SIZE)
    if not _verified_file(vocab_path, _VOCAB_SHA256, _VOCAB_SIZE):
        _download_verified(_VOCAB_URL, vocab_path, _VOCAB_SHA256, _VOCAB_SIZE)
    return os.fspath(model_path)


def load_model_manifest(models: Path | None = None) -> dict[str, Any]:
    models = models if models is not None else models_root()
    path = models / "manifest.json"
    try:
        data = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cortext model manifest unreadable: {path}") from exc
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"cortext model manifest invalid: {path}") from exc


def find_model_asset(manifest: dict[str, Any], filename: str) -> dict[str, Any]:
    for asset in manifest.get("assets") or []:
        if asset.get("filename") == filename:
            return asset
    raise RuntimeError(f"cortext model asset not declared: {filename}")


def _cached_materialized(cache_dir: Path) -> str | None:
    key = str(cache_dir)
    path = _materialized_cache.get(key)
    if not path:
        return None
    if not Path(path).is_file():
        _materialized_cache.pop(key, None)
        return None
    return path


def ensure_vocab_in_cache(
    cache_dir: Path, manifest: dict[str, Any], models: Path
) -> None:
    asset = find_model_asset(manifest, VOCAB_ASSET_NAME)
    dest = cache_dir / Path(VOCAB_ASSET_NAME)
    want = str(asset["sha256"])
    ok, _ = file_has_sha256(dest, want)
    if ok:
        return
    src = models / Path(VOCAB_ASSET_NAME)
    ok, actual = file_has_sha256(src, want)
    if not ok:
        if actual == "":
            raise RuntimeError(f"cortext vocab asset missing: {VOCAB_ASSET_NAME}")
        raise RuntimeError(f"cortext vocab checksum mismatch: {VOCAB_ASSET_NAME}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def materialize_model(db_path: str = ":memory:") -> str:
    """Reassemble release AIST chunks into a local cache; return .gguf path.

    Never downloads. Verifies each chunk SHA-256 and the reassembled model.
    """
    cache_dir = model_cache_dir(db_path)
    cached = _cached_materialized(cache_dir)
    if cached is not None:
        return cached

    with _materialize_lock:
        cached = _cached_materialized(cache_dir)
        if cached is not None:
            return cached
        path = _materialize_model_locked(cache_dir)
        _materialized_cache[str(cache_dir)] = path
        return path


def _materialize_model_locked(cache_dir: Path) -> str:
    models = models_root()
    manifest = load_model_manifest(models)
    asset = find_model_asset(manifest, MODEL_ASSET_NAME)
    chunks = asset.get("chunks") or []
    if not chunks:
        raise RuntimeError(f"cortext model asset {MODEL_ASSET_NAME} has no chunks declared")

    model_path = cache_dir / Path(MODEL_ASSET_NAME)
    want_sha = str(asset["sha256"])
    ok, _ = file_has_sha256(model_path, want_sha)
    if ok:
        ensure_vocab_in_cache(cache_dir, manifest, models)
        return os.fspath(model_path)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_vocab_in_cache(cache_dir, manifest, models)

    fd, tmp_name = tempfile.mkstemp(
        prefix=".aist-",
        suffix=".tmp",
        dir=os.fspath(model_path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    hasher = hashlib.sha256()
    try:
        with tmp_path.open("wb") as out:
            for chunk in chunks:
                rel = str(chunk["filename"])
                chunk_path = models / Path(rel)
                want_chunk = str(chunk["sha256"])
                ok, actual = file_has_sha256(chunk_path, want_chunk)
                if not ok:
                    if actual == "":
                        raise RuntimeError(f"cortext model chunk missing: {rel}")
                    raise RuntimeError(
                        f"cortext model chunk checksum mismatch: {rel} (got {actual})"
                    )
                with chunk_path.open("rb") as handle:
                    while True:
                        block = handle.read(1024 * 1024)
                        if not block:
                            break
                        out.write(block)
                        hasher.update(block)
        actual = hasher.hexdigest()
        if actual != want_sha:
            raise RuntimeError(
                f"cortext reassembled model checksum mismatch: got {actual} want {want_sha}"
            )
        tmp_path.replace(model_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return os.fspath(model_path)


def resolve_aist_model(db_path: str = ":memory:") -> str:
    """Resolve a verified model from shipped chunks or the pinned PyPI cache.

    Full GitHub Release wheels materialize their shipped chunks. The slim PyPI
    wheel downloads the same pinned assets on first use.
    """
    if chunks_ready():
        return materialize_model(db_path)
    with _materialize_lock:
        return _remote_model_path(model_cache_dir(db_path))


def clear_materialize_cache(cache_dir: Path | str | None = None) -> None:
    """Drop memoized materialize paths (used by tests with temp caches)."""
    if cache_dir is None:
        _materialized_cache.clear()
        return
    _materialized_cache.pop(str(Path(cache_dir)), None)
