"""AIST model materialize from **shipped** package model chunks.

Chunks live under ``cortext/models/`` (package data). No network or sibling search.

The engine's late-interaction reranker (``AIST-87M-LI.gguf``) must resolve
whenever an AIST model is used. It is placed beside the materialized AIST model,
where the engine looks for it, unless ``CORTEXT_LI_MODEL_PATH`` names it.
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
LI_MODEL_ASSET_NAME = "AIST-87M-GGUF/AIST-87M-LI.gguf"
LI_MODEL_ENV = "CORTEXT_LI_MODEL_PATH"

_materialize_lock = threading.Lock()
# cache_dir -> (AIST path, LI path the manifest places beside it or None)
_materialized_cache: dict[str, tuple[str, str | None]] = {}

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
# The reranker is not on the Hugging Face model repo; it ships as a Git shard
# in augmem/cortext.cpp. Pinned to an immutable commit and verified by size
# and SHA-256 (its single shard is the whole file).
_LI_MODEL_URL = (
    "https://raw.githubusercontent.com/augmem/cortext.cpp/"
    "f0b681e97450a4955458d0f4b140f58d15bba650/"
    "models/AIST-87M-GGUF/chunks/AIST-87M-LI.gguf.part-000"
)
_LI_MODEL_SHA256 = "e5fc69ab84fbfe826a4730346b9a9315f12dc1e11767c66d5bc38557ef4290a4"
_LI_MODEL_SIZE = 410848
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


def li_model_override() -> Path | None:
    """``CORTEXT_LI_MODEL_PATH`` when set, with ``~`` expanded.

    The engine reads the raw variable, so ``Cortext`` writes this expanded
    path back into the environment for the duration of engine creation.
    """
    value = os.environ.get(LI_MODEL_ENV)
    return Path(value).expanduser() if value else None


def _remote_model_path(cache_dir: Path) -> str:
    model_path = cache_dir / Path(MODEL_ASSET_NAME)
    vocab_path = cache_dir / Path(VOCAB_ASSET_NAME)
    li_path = cache_dir / Path(LI_MODEL_ASSET_NAME)
    if not _verified_file(model_path, _AIST_MODEL_SHA256, _AIST_MODEL_SIZE):
        _download_verified(_AIST_MODEL_URL, model_path, _AIST_MODEL_SHA256, _AIST_MODEL_SIZE)
    if not _verified_file(vocab_path, _VOCAB_SHA256, _VOCAB_SIZE):
        _download_verified(_VOCAB_URL, vocab_path, _VOCAB_SHA256, _VOCAB_SIZE)
    if li_model_override() is None and not _verified_file(
        li_path, _LI_MODEL_SHA256, _LI_MODEL_SIZE
    ):
        _download_verified(_LI_MODEL_URL, li_path, _LI_MODEL_SHA256, _LI_MODEL_SIZE)
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
    asset = _declared_model_asset(manifest, filename)
    if asset is None:
        raise RuntimeError(f"cortext model asset not declared: {filename}")
    return asset


def _declared_model_asset(
    manifest: dict[str, Any], filename: str
) -> dict[str, Any] | None:
    for asset in manifest.get("assets") or []:
        if asset.get("filename") == filename:
            return asset
    return None


def _cached_materialized(cache_dir: Path) -> str | None:
    key = str(cache_dir)
    entry = _materialized_cache.get(key)
    if not entry:
        return None
    path, li_path = entry
    li_missing = (
        li_path is not None
        and li_model_override() is None
        and not Path(li_path).is_file()
    )
    if not Path(path).is_file() or li_missing:
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
        path, li_path = _materialize_model_locked(cache_dir)
        _materialized_cache[str(cache_dir)] = (path, li_path)
        return path


def _materialize_model_locked(cache_dir: Path) -> tuple[str, str | None]:
    models = models_root()
    manifest = load_model_manifest(models)
    asset = find_model_asset(manifest, MODEL_ASSET_NAME)
    model_path = cache_dir / Path(MODEL_ASSET_NAME)
    ensure_vocab_in_cache(cache_dir, manifest, models)
    _reassemble_asset(models, asset, model_path)
    li_path = _ensure_li_model_beside(model_path, manifest, models)
    return os.fspath(model_path), li_path


def _ensure_li_model_beside(
    model_path: Path, manifest: dict[str, Any], models: Path
) -> str | None:
    """Reassemble the reranker beside AIST when the manifest declares it.

    Returns where the manifest places it (``None`` for engine releases whose
    manifest predates it). Placement is skipped while
    ``CORTEXT_LI_MODEL_PATH`` names the reranker.
    """
    asset = _declared_model_asset(manifest, LI_MODEL_ASSET_NAME)
    if asset is None:
        return None
    li_path = model_path.parent / Path(LI_MODEL_ASSET_NAME).name
    if li_model_override() is None:
        _reassemble_asset(models, asset, li_path)
    return os.fspath(li_path)


def _reassemble_asset(models: Path, asset: dict[str, Any], dest: Path) -> None:
    """Concatenate an asset's verified chunks into ``dest`` (idempotent)."""
    name = str(asset["filename"])
    chunks = asset.get("chunks") or []
    if not chunks:
        raise RuntimeError(f"cortext model asset {name} has no chunks declared")
    want_sha = str(asset["sha256"])
    ok, _ = file_has_sha256(dest, want_sha)
    if ok:
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.stem}-",
        suffix=".tmp",
        dir=os.fspath(dest.parent),
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
                f"cortext reassembled {name} checksum mismatch: "
                f"got {actual} want {want_sha}"
            )
        tmp_path.replace(dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def resolve_aist_model(db_path: str = ":memory:") -> str:
    """Resolve a verified model from shipped chunks or the pinned PyPI cache.

    Full GitHub Release wheels materialize their shipped chunks. The slim PyPI
    wheel downloads the same pinned assets on first use.
    """
    if chunks_ready():
        return materialize_model(db_path)
    with _materialize_lock:
        return _remote_model_path(model_cache_dir(db_path))


def resolve_li_model(db_path: str = ":memory:") -> str | None:
    """Path of the late-interaction reranker the engine will load.

    ``CORTEXT_LI_MODEL_PATH`` when set; otherwise ``AIST-87M-LI.gguf`` beside
    the AIST model in effect (``CORTEXT_AIST_MODEL_PATH`` or the resolved
    one, which may reassemble or download it), or ``None`` when no file sits
    there (the engine then uses a reranker linked into the native library).
    """
    override = li_model_override()
    if override is not None:
        return os.fspath(override)
    beside = Path(aist_model_in_effect(db_path)).parent / Path(LI_MODEL_ASSET_NAME).name
    return os.fspath(beside) if beside.is_file() else None


def aist_model_in_effect(db_path: str = ":memory:") -> str:
    """The AIST model ``Cortext`` hands the engine.

    ``CORTEXT_AIST_MODEL_PATH`` when it names an existing file, otherwise the
    model resolved from shipped chunks or the verified cache (which may
    reassemble or download it).
    """
    env = os.environ.get("CORTEXT_AIST_MODEL_PATH")
    if env:
        path = Path(env).expanduser()
        if path.is_file():
            return os.fspath(path)
    return resolve_aist_model(db_path)


def clear_materialize_cache(cache_dir: Path | str | None = None) -> None:
    """Drop memoized materialize paths (used by tests with temp caches)."""
    if cache_dir is None:
        _materialized_cache.clear()
        return
    _materialized_cache.pop(str(Path(cache_dir)), None)
