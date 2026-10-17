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


def test_text_media_capability_only_requires_options_symbol():
    import cortext

    class FakeFunction:
        pass

    class FakeLibrary:
        def __init__(self):
            self.functions = {}

        def __getattr__(self, name):
            if name == "cortext_process_text_with_media_json":
                raise AttributeError(name)
            function = self.functions.setdefault(name, FakeFunction())
            return function

    lib = cortext._configure_library(FakeLibrary())

    assert lib._cortext_text_media_json_available is True
    assert "cortext_process_text_with_media_json_with_options" in lib.functions


def test_process_text_with_media_forwards_binary_bytes_and_mimetype():
    import ctypes

    import cortext

    native_fn = object()
    fake_lib = type("FakeLib", (), {
        "cortext_process_text_with_media_json_with_options": native_fn,
        "_cortext_text_media_json_available": True,
    })()
    engine = object.__new__(cortext.Cortext)
    engine._lib = fake_lib
    engine._handle = None
    captured = {}

    def call_json(fn, *args):
        captured["fn"] = fn
        captured["text"] = args[0]
        captured["source_id"] = args[1]
        media = ctypes.cast(
            args[2], ctypes.POINTER(cortext._NativeMedia)
        ).contents
        captured["media"] = ctypes.string_at(media.data, media.size)
        captured["mimetype"] = ctypes.string_at(media.mimetype)
        return '{"ok": true}'

    engine._call_json = call_json
    payload = b"\x00\xff\x01"

    assert engine.process_text_with_media(
        "text", "source", payload, "application/octet-stream"
    ) == {"ok": True}
    assert captured == {
        "fn": native_fn,
        "text": b"text",
        "source_id": b"source",
        "media": payload,
        "mimetype": b"application/octet-stream",
    }


def test_mixed_memory_returns_every_payload_with_its_mimetype(tmp_path):
    import base64

    import cortext
    from cortext.model import clear_materialize_cache

    os.environ["CORTEXT_MODEL_CACHE_DIR"] = str(tmp_path / "engine-cache-mixed")
    clear_materialize_cache()
    photo = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"
    try:
        with cortext.Cortext(str(tmp_path / "mixed.db")) as engine:
            # One turn = one source: a text signal and its photo, as peers.
            engine.process_text(
                "The parking garage ticket says level 4 spot 27.",
                "chat/user/turn1",
                retention=cortext.Retention.NATURAL,
            )
            engine.process_image_with_media(
                bytes([128]) * (8 * 8 * 3), 8, 8, 3, "chat/user/turn1",
                photo, "image/jpeg", retention=cortext.Retention.DURABLE,
            )
            ctx = engine.process_text(
                "parking garage level spot",
                "query/public",
                retention=cortext.Retention.EPHEMERAL,
            )
        mixed = [
            m
            for m in ctx["retrieved_memory"] + ctx["working_memory"]
            if m["modality"] == "mixed"
        ]
        assert mixed, [m["modality"] for m in ctx["retrieved_memory"]]
        for memory in mixed:
            mimes = [c["mimetype"] for c in memory["content"]]
            assert sorted(mimes) == ["image/jpeg", "text/plain"]
            blobs = {
                c["mimetype"]: base64.b64decode(c["base64"])
                for c in memory["content"]
            }
            assert blobs["image/jpeg"] == photo
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


def test_augmem_namespace_compatibility():
    import augmem.cortext as compat
    import cortext

    assert compat.Cortext is cortext.Cortext
    assert compat.Media is cortext.Media


def test_model_resolution_falls_back_to_verified_cache(monkeypatch, tmp_path):
    import cortext.model as model

    expected = tmp_path / "AIST-87M_q8_0.gguf"
    expected.write_bytes(b"verified-test-placeholder")
    monkeypatch.setenv("CORTEXT_MODEL_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(model, "chunks_ready", lambda: False)
    monkeypatch.setattr(model, "_remote_model_path", lambda _cache: str(expected))

    assert model.resolve_aist_model() == str(expected)
