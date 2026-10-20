"""Real-path tests against **shipped** package natives + model chunks."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_WORKSPACE = Path(__file__).resolve().parents[1]
_PKG = _WORKSPACE / "cortext"


@pytest.fixture(scope="module", autouse=True)
def _clear_override_env():
    """Shipped path must work without CORTEXT_ASSETS_DIR.

    ``CORTEXT_LIBRARY_PATH`` is kept: it is how a maintainer points the suite
    at a locally built engine (it wins over the shipped native).
    """
    prev_assets = os.environ.pop("CORTEXT_ASSETS_DIR", None)
    import cortext as ct

    ct._LIB = None  # type: ignore[attr-defined]
    yield
    if prev_assets is not None:
        os.environ["CORTEXT_ASSETS_DIR"] = prev_assets
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
    assert (
        _PKG / "models" / "AIST-87M-GGUF" / "chunks" / "AIST-87M-LI.gguf.part-000"
    ).is_file()

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
        li = path.parent / "AIST-87M-LI.gguf"
        if os.environ.get("CORTEXT_LI_MODEL_PATH"):
            assert not li.exists()
        else:
            assert li.stat().st_size == 410848
            assert sha256_file(li) == (
                "e5fc69ab84fbfe826a4730346b9a9315f12dc1e11767c66d5bc38557ef4290a4"
            )
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


def test_process_json_options_carry_the_evidence_budget():
    import ctypes

    import cortext

    unset = cortext._native_process_json_options(True)
    assert unset.struct_size == ctypes.sizeof(cortext._NativeProcessJsonOptions)
    assert unset.evidence_budget_bytes == 0
    budgeted = cortext._native_process_json_options(
        False, cortext.Retention.EPHEMERAL, 34_800
    )
    assert budgeted.evidence_budget_bytes == 34_800
    assert budgeted.retention == int(cortext.Retention.EPHEMERAL)
    for bad in (0, -1):
        with pytest.raises(ValueError):
            cortext._native_process_json_options(True, None, bad)
    with pytest.raises(TypeError):
        cortext._native_process_json_options(True, None, 1.5)


def test_evidence_budget_bounds_standing_and_retrieved(tmp_path):
    import base64

    import cortext
    from cortext.model import clear_materialize_cache

    os.environ["CORTEXT_MODEL_CACHE_DIR"] = str(tmp_path / "engine-cache-budget")
    clear_materialize_cache()

    def evidence(ctx):
        return sum(
            len(base64.b64decode(c["base64"]))
            if c["mimetype"].startswith("text/")
            else 480
            for m in ctx["standing_memory"] + ctx["retrieved_memory"]
            for c in m["content"]
        )

    try:
        with cortext.Cortext(str(tmp_path / "budget.db")) as engine:
            engine.process_text(
                "Always answer with the departure pier.", "chat/rules",
                retention=cortext.Retention.DURABLE,
            )
            for i in range(6):
                engine.process_text(
                    f"The ferry to the island leaves at {6 + i} from pier four.",
                    f"chat/ferry/{i}",
                    retention=cortext.Retention.DURABLE,
                )
            query = "When does the ferry leave?"
            whole = engine.process_text(
                query, "query/public", retention=cortext.Retention.EPHEMERAL
            )
            assert "standing_memory" in whole
            assert len(whole["retrieved_memory"]) >= 2
            budget = evidence(whole) // 2
            budgeted = engine.process_text(
                query, "query/public",
                retention=cortext.Retention.EPHEMERAL,
                evidence_budget_bytes=budget,
            )
        assert evidence(budgeted) <= budget
        assert len(budgeted["retrieved_memory"]) < len(whole["retrieved_memory"])
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


def test_native_struct_layouts_match_capi():
    """Mirrors of cortext_config / cortext_process_json_options (capi.h)."""
    import ctypes

    import cortext

    config_fields = [name for name, _ in cortext._NativeConfig._fields_]
    assert "procedural_enabled" not in config_fields
    assert ctypes.sizeof(cortext._NativeConfig) == 64

    options = cortext._NativeProcessJsonOptions
    assert ctypes.sizeof(options) == 48
    assert options.evidence_budget_bytes.offset == 24
    assert options.has_reference_ms.offset == 32
    assert options.as_of.offset == 36
    assert options.reference_ms.offset == 40


def test_process_json_options_carry_the_reference_time():
    from datetime import datetime, timedelta, timezone

    import cortext

    unset = cortext._native_process_json_options(True)
    assert (unset.has_reference_ms, unset.as_of, unset.reference_ms) == (0, 0, 0)

    at_ms = cortext._native_process_json_options(
        True, cortext.Retention.EPHEMERAL, reference_time=1_700_000_000_123
    )
    assert (at_ms.has_reference_ms, at_ms.as_of, at_ms.reference_ms) == (
        1, 0, 1_700_000_000_123
    )

    moment = datetime(2023, 11, 14, 22, 13, 20, 123000, tzinfo=timezone.utc)
    as_of = cortext._native_process_json_options(
        True, cortext.Retention.EPHEMERAL, reference_time=moment, as_of=True
    )
    assert (as_of.has_reference_ms, as_of.as_of, as_of.reference_ms) == (
        1, 1, 1_700_000_000_123
    )
    offset = moment.astimezone(timezone(timedelta(hours=-5)))
    assert (
        cortext._native_process_json_options(True, reference_time=offset).reference_ms
        == 1_700_000_000_123
    )

    with pytest.raises(ValueError):
        cortext._native_process_json_options(True, as_of=True)
    with pytest.raises(ValueError):
        cortext._native_process_json_options(True, reference_time=-1)
    with pytest.raises(ValueError):
        cortext._native_process_json_options(
            True, reference_time=datetime(2023, 11, 14)
        )
    with pytest.raises(TypeError):
        cortext._native_process_json_options(True, reference_time=1.5)
    with pytest.raises(TypeError):
        cortext._native_process_json_options(True, reference_time=True)


def _store_ferry_timetable(engine):
    import cortext

    engine.process_text(
        "Always answer with the departure pier.", "chat/rules",
        retention=cortext.Retention.DURABLE,
    )
    for i in range(3):
        engine.process_text(
            f"The ferry to the island leaves at {6 + i} from pier four.",
            f"chat/ferry/{i}",
            retention=cortext.Retention.DURABLE,
        )


def test_reference_time_with_and_without_as_of(tmp_path):
    from datetime import datetime, timedelta, timezone

    import cortext
    from cortext.model import clear_materialize_cache

    os.environ["CORTEXT_MODEL_CACHE_DIR"] = str(tmp_path / "engine-cache-reftime")
    clear_materialize_cache()
    query = "When does the ferry leave?"
    try:
        with cortext.Cortext(str(tmp_path / "reftime.db")) as engine:
            stored_at = datetime.now(timezone.utc)
            _store_ferry_timetable(engine)
            before = stored_at - timedelta(days=1)
            after = datetime.now(timezone.utc) + timedelta(days=1)

            def ask(**kwargs):
                return engine.process_text(
                    query, "query/public",
                    retention=cortext.Retention.EPHEMERAL, **kwargs,
                )

            unchanged = ask()
            past = ask(reference_time=before)
            past_as_of = ask(reference_time=before, as_of=True)
            future_as_of = ask(reference_time=after, as_of=True)
            past_ms_as_of = ask(
                reference_time=int(before.timestamp() * 1000), as_of=True
            )

        assert unchanged["retrieved_memory"]
        assert unchanged["standing_memory"]
        # A reference time alone only adds candidates near it.
        assert past["retrieved_memory"]
        # As of a moment before anything was stored, nothing is visible yet.
        assert past_as_of["retrieved_memory"] == []
        assert past_as_of["standing_memory"] == []
        assert past_ms_as_of["retrieved_memory"] == []
        # As of a later moment, everything stored so far is visible.
        assert {m["id"] for m in future_as_of["retrieved_memory"]} == {
            m["id"] for m in unchanged["retrieved_memory"]
        }
    finally:
        os.environ.pop("CORTEXT_MODEL_CACHE_DIR", None)
        clear_materialize_cache()


def test_content_entries_carry_their_timestamps(tmp_path):
    import time

    import cortext
    from cortext.model import clear_materialize_cache

    os.environ["CORTEXT_MODEL_CACHE_DIR"] = str(tmp_path / "engine-cache-ts")
    clear_materialize_cache()
    try:
        with cortext.Cortext(str(tmp_path / "ts.db")) as engine:
            start_ms = int(time.time() * 1000)
            _store_ferry_timetable(engine)
            end_ms = int(time.time() * 1000)
            ctx = engine.process_text(
                "When does the ferry leave?", "query/public",
                retention=cortext.Retention.EPHEMERAL,
            )
        memories = ctx["standing_memory"] + ctx["retrieved_memory"]
        assert memories
        for memory in memories:
            assert memory["content"]
            for entry in memory["content"]:
                assert isinstance(entry["timestamp"], int)
                assert start_ms <= entry["timestamp"] <= end_ms
    finally:
        os.environ.pop("CORTEXT_MODEL_CACHE_DIR", None)
        clear_materialize_cache()


def test_standing_memory_is_separate_from_retrieved(tmp_path):
    import base64

    import cortext
    from cortext.model import clear_materialize_cache

    os.environ["CORTEXT_MODEL_CACHE_DIR"] = str(tmp_path / "engine-cache-standing")
    clear_materialize_cache()
    directive = "Always answer with the departure pier."
    try:
        with cortext.Cortext(str(tmp_path / "standing.db")) as engine:
            _store_ferry_timetable(engine)
            ctx = engine.process_text(
                "When does the ferry leave?", "query/public",
                retention=cortext.Retention.EPHEMERAL,
            )

        def texts(memories):
            return [
                base64.b64decode(c["base64"]).decode("utf-8")
                for m in memories
                for c in m["content"]
            ]

        # Standing directives come back in their own block, which holds only
        # the signals that state a directive (never the plain facts).
        assert texts(ctx["standing_memory"]) == [directive]
        assert any("ferry" in t for t in texts(ctx["retrieved_memory"]))
    finally:
        os.environ.pop("CORTEXT_MODEL_CACHE_DIR", None)
        clear_materialize_cache()


def test_text_with_media_stores_caller_bytes_or_canonical_text(tmp_path):
    import base64

    import cortext
    from cortext.model import clear_materialize_cache

    os.environ["CORTEXT_MODEL_CACHE_DIR"] = str(tmp_path / "engine-cache-media")
    clear_materialize_cache()
    pdf = b"%PDF-1.7 fake boarding pass"
    markdown = "# Boarding\n\nGate **B12** for the ferry to the island."
    try:
        with cortext.Cortext(str(tmp_path / "media.db")) as engine:
            engine.process_text_with_media(
                "Boarding pass for the ferry to the island, gate B12.",
                "chat/pass",
                cortext.Media(pdf, "application/pdf"),
                retention=cortext.Retention.DURABLE,
            )
            engine.process_text_with_media(
                "The ferry snack bar opens at noon.",
                "chat/snacks",
                b"",
                retention=cortext.Retention.DURABLE,
            )
            engine.process_text_with_media(
                "Boarding notes for the island ferry gate.",
                "chat/notes",
                markdown.encode("utf-8"),
                "text/markdown",
                retention=cortext.Retention.DURABLE,
                evidence_budget_bytes=None,
            )
            ctx = engine.process_text(
                "ferry island boarding gate snack bar", "query/public",
                retention=cortext.Retention.EPHEMERAL,
            )
        by_source = {
            m["source_id"]: m["content"]
            for m in ctx["retrieved_memory"] + ctx["working_memory"]
        }
        assert {"chat/pass", "chat/snacks", "chat/notes"} <= set(by_source)
        (pass_entry,) = by_source["chat/pass"]
        assert pass_entry["mimetype"] == "application/pdf"
        assert base64.b64decode(pass_entry["base64"]) == pdf
        (snack_entry,) = by_source["chat/snacks"]
        assert snack_entry["mimetype"].startswith("text/plain")
        assert (
            base64.b64decode(snack_entry["base64"]).decode("utf-8")
            == "The ferry snack bar opens at noon."
        )
        (notes_entry,) = by_source["chat/notes"]
        assert notes_entry["mimetype"] == "text/markdown"
        assert base64.b64decode(notes_entry["base64"]).decode("utf-8") == markdown
    finally:
        os.environ.pop("CORTEXT_MODEL_CACHE_DIR", None)
        clear_materialize_cache()


def _fake_models_tree(root, *, with_li=True, li_chunk_sha=None):
    """A tiny models/ tree shaped like the engine's manifest.json."""
    import hashlib
    import json

    def sha(data):
        return hashlib.sha256(data).hexdigest()

    aist = [b"aist-part-0|", b"aist-part-1"]
    li = b"late-interaction-reranker"
    vocab = b"[PAD]\n[UNK]\n"
    chunks = root / "AIST-87M-GGUF" / "chunks"
    chunks.mkdir(parents=True)
    for i, part in enumerate(aist):
        (chunks / f"AIST-87M_q8_0.gguf.part-{i:03d}").write_bytes(part)
    (root / "mdbr-leaf-ir").mkdir()
    (root / "mdbr-leaf-ir" / "vocab.txt").write_bytes(vocab)
    assets = [
        {
            "filename": "AIST-87M-GGUF/AIST-87M_q8_0.gguf",
            "sha256": sha(b"".join(aist)),
            "size": len(b"".join(aist)),
            "chunks": [
                {
                    "filename": f"AIST-87M-GGUF/chunks/AIST-87M_q8_0.gguf.part-{i:03d}",
                    "sha256": sha(part),
                }
                for i, part in enumerate(aist)
            ],
        },
        {"filename": "mdbr-leaf-ir/vocab.txt", "sha256": sha(vocab)},
    ]
    if with_li:
        (chunks / "AIST-87M-LI.gguf.part-000").write_bytes(li)
        assets.append(
            {
                "filename": "AIST-87M-GGUF/AIST-87M-LI.gguf",
                "sha256": sha(li),
                "size": len(li),
                "chunks": [
                    {
                        "filename": "AIST-87M-GGUF/chunks/AIST-87M-LI.gguf.part-000",
                        "sha256": li_chunk_sha or sha(li),
                    }
                ],
            }
        )
    (root / "manifest.json").write_text(
        json.dumps({"schema": "augmem.cortext.models.v1", "assets": assets})
    )
    return li


def test_materialize_places_the_li_model_beside_aist(monkeypatch, tmp_path):
    import cortext.model as model

    models = tmp_path / "models"
    li = _fake_models_tree(models)
    cache = tmp_path / "cache"
    monkeypatch.setattr(model, "models_root", lambda: models)
    monkeypatch.setenv("CORTEXT_MODEL_CACHE_DIR", str(cache))
    monkeypatch.delenv("CORTEXT_LI_MODEL_PATH", raising=False)
    model.clear_materialize_cache()
    try:
        aist_path = Path(model.materialize_model())
        li_path = aist_path.parent / "AIST-87M-LI.gguf"
        assert li_path.read_bytes() == li
        assert model.resolve_li_model() == str(li_path)
    finally:
        model.clear_materialize_cache()


def test_materialize_rejects_a_corrupt_li_chunk(monkeypatch, tmp_path):
    import cortext.model as model

    models = tmp_path / "models"
    _fake_models_tree(models, li_chunk_sha="0" * 64)
    monkeypatch.setattr(model, "models_root", lambda: models)
    monkeypatch.setenv("CORTEXT_MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("CORTEXT_LI_MODEL_PATH", raising=False)
    model.clear_materialize_cache()
    try:
        with pytest.raises(RuntimeError, match="AIST-87M-LI"):
            model.materialize_model()
    finally:
        model.clear_materialize_cache()


def test_materialize_without_a_declared_li_asset_skips_it(monkeypatch, tmp_path):
    """Engine releases before the reranker declare no LI asset."""
    import cortext.model as model

    models = tmp_path / "models"
    _fake_models_tree(models, with_li=False)
    monkeypatch.setattr(model, "models_root", lambda: models)
    monkeypatch.setenv("CORTEXT_MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("CORTEXT_LI_MODEL_PATH", raising=False)
    model.clear_materialize_cache()
    try:
        aist_path = Path(model.materialize_model())
        assert aist_path.is_file()
        assert not (aist_path.parent / "AIST-87M-LI.gguf").exists()
    finally:
        model.clear_materialize_cache()


def test_li_model_path_override_wins_over_shipped_chunks(monkeypatch, tmp_path):
    import cortext.model as model

    models = tmp_path / "models"
    _fake_models_tree(models, li_chunk_sha="0" * 64)  # would fail if read
    override = tmp_path / "custom-LI.gguf"
    override.write_bytes(b"caller-supplied reranker")
    monkeypatch.setattr(model, "models_root", lambda: models)
    monkeypatch.setenv("CORTEXT_MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("CORTEXT_LI_MODEL_PATH", str(override))
    model.clear_materialize_cache()
    try:
        aist_path = Path(model.materialize_model())
        assert not (aist_path.parent / "AIST-87M-LI.gguf").exists()
        assert model.resolve_li_model() == str(override)
    finally:
        model.clear_materialize_cache()


def test_missing_li_model_path_override_fails_fast(monkeypatch, tmp_path):
    import cortext

    monkeypatch.setenv("CORTEXT_LI_MODEL_PATH", str(tmp_path / "missing-LI.gguf"))
    with pytest.raises(cortext.CortextError, match="CORTEXT_LI_MODEL_PATH"):
        cortext.Cortext(":memory:")


def test_remote_bootstrap_downloads_the_li_model_beside_aist(monkeypatch, tmp_path):
    import cortext.model as model

    calls = []

    def fake_download(url, dest, sha256, size):
        calls.append((url, dest, sha256, size))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")

    monkeypatch.delenv("CORTEXT_LI_MODEL_PATH", raising=False)
    monkeypatch.setattr(model, "_verified_file", lambda *_args: False)
    monkeypatch.setattr(model, "_download_verified", fake_download)
    aist_path = Path(model._remote_model_path(tmp_path))

    by_url = {url: (dest, sha, size) for url, dest, sha, size in calls}
    li_dest, li_sha, li_size = by_url[model._LI_MODEL_URL]
    assert li_dest == aist_path.parent / "AIST-87M-LI.gguf"
    assert li_sha == model._LI_MODEL_SHA256
    assert li_size == model._LI_MODEL_SIZE
    assert model._AIST_MODEL_URL in by_url


def test_pinned_li_checksum_matches_the_engine_model():
    """Runs when CORTEXT_LI_MODEL_PATH points at the engine's assembled LI."""
    import cortext.model as model

    path = os.environ.get("CORTEXT_LI_MODEL_PATH")
    if not path or not Path(path).is_file():
        pytest.skip("CORTEXT_LI_MODEL_PATH not set to an assembled LI model")
    assert Path(path).stat().st_size == model._LI_MODEL_SIZE
    assert model.sha256_file(Path(path)) == model._LI_MODEL_SHA256


def test_materialize_memo_replaces_a_missing_li_model(monkeypatch, tmp_path):
    import cortext.model as model

    models = tmp_path / "models"
    li = _fake_models_tree(models)
    monkeypatch.setattr(model, "models_root", lambda: models)
    monkeypatch.setenv("CORTEXT_MODEL_CACHE_DIR", str(tmp_path / "cache"))
    model.clear_materialize_cache()
    try:
        # First call while an override names the reranker: nothing placed.
        monkeypatch.setenv("CORTEXT_LI_MODEL_PATH", str(tmp_path / "custom-LI.gguf"))
        li_path = Path(model.materialize_model()).parent / "AIST-87M-LI.gguf"
        assert not li_path.exists()
        # Override dropped: the memoized call must still place it.
        monkeypatch.delenv("CORTEXT_LI_MODEL_PATH")
        model.materialize_model()
        assert li_path.read_bytes() == li
        # Deleted after placement: placed again.
        li_path.unlink()
        model.materialize_model()
        assert li_path.read_bytes() == li
    finally:
        model.clear_materialize_cache()


def test_resolve_li_model_looks_beside_the_aist_model_in_effect(monkeypatch, tmp_path):
    import cortext.model as model

    aist = tmp_path / "custom" / "AIST.gguf"
    aist.parent.mkdir()
    aist.write_bytes(b"caller-supplied aist")
    monkeypatch.delenv("CORTEXT_LI_MODEL_PATH", raising=False)
    monkeypatch.setenv("CORTEXT_AIST_MODEL_PATH", str(aist))

    def unexpected(*_args):
        raise AssertionError("must not resolve a packaged model")

    monkeypatch.setattr(model, "resolve_aist_model", unexpected)
    assert model.resolve_li_model() is None
    beside = aist.parent / "AIST-87M-LI.gguf"
    beside.write_bytes(b"reranker")
    assert model.resolve_li_model() == str(beside)


def test_li_model_path_with_tilde_reaches_the_engine_expanded(monkeypatch, tmp_path):
    import shutil

    import cortext
    from cortext.model import clear_materialize_cache, materialize_model

    monkeypatch.setenv("CORTEXT_MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("CORTEXT_LI_MODEL_PATH", raising=False)
    clear_materialize_cache()
    try:
        shipped_li = Path(materialize_model()).parent / "AIST-87M-LI.gguf"
        home = tmp_path / "home"
        home.mkdir()
        shutil.copy2(shipped_li, home / "AIST-87M-LI.gguf")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("CORTEXT_LI_MODEL_PATH", "~/AIST-87M-LI.gguf")
        assert cortext.resolve_li_model() == str(home / "AIST-87M-LI.gguf")
        with cortext.Cortext(":memory:") as engine:
            assert engine.embed_text("tilde path")
        # The caller's raw value is restored after engine creation.
        assert os.environ["CORTEXT_LI_MODEL_PATH"] == "~/AIST-87M-LI.gguf"
    finally:
        clear_materialize_cache()
