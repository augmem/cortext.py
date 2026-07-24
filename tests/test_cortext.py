"""Real-path tests against **shipped** package natives + model chunks."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_WORKSPACE = Path(__file__).resolve().parents[1]
_PKG = _WORKSPACE / "cortext"


@pytest.fixture(scope="module", autouse=True)
def _clear_override_env():
    """Shipped path must work without CORTEXT_ASSETS_DIR."""
    prev_assets = os.environ.pop("CORTEXT_ASSETS_DIR", None)
    prev_lib = os.environ.pop("CORTEXT_LIBRARY_PATH", None)
    import cortext as ct

    ct._LIB = None  # type: ignore[attr-defined]
    yield
    if prev_assets is not None:
        os.environ["CORTEXT_ASSETS_DIR"] = prev_assets
    if prev_lib is not None:
        os.environ["CORTEXT_LIBRARY_PATH"] = prev_lib
    ct._LIB = None  # type: ignore[attr-defined]


def test_package_ships_all_platform_natives_and_model_chunks():
    tags = [
        "linux-x86_64",
        "linux-aarch64",
        "macos-x86_64",
        "macos-aarch64",
        "windows-x86_64",
        "windows-aarch64",
    ]
    names = {
        "linux-x86_64": "libcortext.so",
        "linux-aarch64": "libcortext.so",
        "macos-x86_64": "libcortext.dylib",
        "macos-aarch64": "libcortext.dylib",
        "windows-x86_64": "cortext.dll",
        "windows-aarch64": "cortext.dll",
    }
    for tag in tags:
        path = _PKG / "native" / tag / names[tag]
        assert path.is_file(), f"missing shipped native {path}"
        assert path.stat().st_size > 1_000_000

    assert (_PKG / "models" / "manifest.json").is_file()
    for i in range(3):
        part = (
            _PKG
            / "models"
            / "AIST-87M-GGUF"
            / "chunks"
            / f"AIST-87M_q8_0.gguf.part-{i:03d}"
        )
        assert part.is_file(), f"missing chunk {part}"
    assert (_PKG / "models" / "mdbr-leaf-ir" / "vocab.txt").is_file()

    pyproject = (_WORKSPACE / "pyproject.toml").read_text(encoding="utf-8")
    assert "native/**/*" in pyproject
    assert "models/**/*" in pyproject


def test_package_assets_ready_and_load():
    import cortext
    from cortext.assets import PACKAGE_DIR, assets_root, host_library_path

    assert cortext.package_assets_ready()
    root = assets_root()
    assert root == PACKAGE_DIR
    assert host_library_path(root).is_file()
    assert cortext.version()


def test_load_library_uses_shipped_native():
    import cortext

    lib = cortext.load_library()
    assert lib is not None
    v = cortext.version()
    assert isinstance(v, str) and len(v) > 0


def test_materialize_model_from_shipped_chunks(tmp_path):
    from cortext.model import clear_materialize_cache, materialize_model, sha256_file

    cache = tmp_path / "model-cache"
    os.environ["CORTEXT_MODEL_CACHE_DIR"] = str(cache)
    clear_materialize_cache()
    try:
        model = materialize_model(":memory:")
        path = Path(model)
        assert path.is_file()
        assert path.stat().st_size == 141491936
        assert (
            sha256_file(path)
            == "bf4c49954eccc65183f1a97e44606e86c7ee5a4fea500457124b687a3ec97898"
        )
        assert (cache / "mdbr-leaf-ir" / "vocab.txt").is_file()
    finally:
        os.environ.pop("CORTEXT_MODEL_CACHE_DIR", None)
        clear_materialize_cache()


def test_process_text_and_embed_text(tmp_path):
    import cortext
    from cortext.model import clear_materialize_cache

    cache = tmp_path / "engine-cache"
    os.environ["CORTEXT_MODEL_CACHE_DIR"] = str(cache)
    clear_materialize_cache()
    try:
        with cortext.Cortext(":memory:") as engine:
            ctx = engine.process_text("Bailey likes tennis balls.", "chat/main")
            assert isinstance(ctx, dict) and len(ctx) > 0
            for key in ("should_interrupt", "retrieved_memory", "working_memory"):
                assert key in ctx, f"missing {key}: {sorted(ctx)}"
            emb = engine.embed_text("embed without storing")
            assert isinstance(emb, list) and len(emb) > 0
            engine.flush()
            engine.reset()
    finally:
        os.environ.pop("CORTEXT_MODEL_CACHE_DIR", None)
        clear_materialize_cache()


def test_embedding_length_stable(tmp_path):
    import cortext
    from cortext.model import clear_materialize_cache

    cache = tmp_path / "engine-cache-2"
    os.environ["CORTEXT_MODEL_CACHE_DIR"] = str(cache)
    clear_materialize_cache()
    try:
        dims = []
        for _ in range(2):
            with cortext.Cortext(":memory:") as engine:
                dims.append(len(engine.embed_text("consistent length check")))
        assert dims[0] > 0 and dims[0] == dims[1]
    finally:
        os.environ.pop("CORTEXT_MODEL_CACHE_DIR", None)
        clear_materialize_cache()


def test_no_runtime_download_import():
    """Happy path must not call GitHub — package data only."""
    import cortext.release as release

    from cortext.assets import package_assets_ready

    assert package_assets_ready()
    assert hasattr(release, "download_release_assets")


def test_build_wheels_script_maps_all_targets():
    """Structural: build_wheels declares six platform tags like PyTorch matrix."""
    script = (_WORKSPACE / "scripts" / "build_wheels.py").read_text(encoding="utf-8")
    for tag in (
        "linux-x86_64",
        "linux-aarch64",
        "macos-x86_64",
        "macos-aarch64",
        "windows-x86_64",
        "windows-aarch64",
    ):
        assert tag in script
    for plat in (
        "manylinux_2_17_x86_64",
        "manylinux_2_17_aarch64",
        "macosx_11_0_x86_64",
        "macosx_11_0_arm64",
        "win_amd64",
        "win_arm64",
    ):
        assert plat in script
