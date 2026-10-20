# Changelog

## Unreleased

Tracks cortext.cpp `main` (engine v5, per-blob content timestamps and
reference-time retrieval). **Requires the next engine release**: no engine
release contains these features yet, so the package version and the pinned
engine (`v1.3.0`) are unchanged, and these features need a native built from
cortext.cpp `main` (point `CORTEXT_LIBRARY_PATH` at it).

### Breaking

- `Config.procedural_enabled` is removed, and the `cortext_config` ctypes
  mirror drops the field to match the engine's C struct layout.
- Soft Anchors are gone from the engine (config stats, memory fields and JSON
  keys). The binding never exposed them, but code reading those keys from the
  returned context must stop.
- Memories are no longer trimmed to 3 KiB each: recalled memories come back
  whole unless `evidence_budget_bytes` is set.
- The engine now requires the late-interaction reranker `AIST-87M-LI.gguf`
  whenever an AIST model is present; see "LI model" below.

### Added

- `evidence_budget_bytes` on every `process_*` call: `None` returns memories
  whole; a positive byte count fits `standing_memory` plus `retrieved_memory`
  within it (text by its UTF-8 bytes, other payloads 480 bytes each).
- `standing_memory`: query contexts return standing directives in their own
  block, outside (and not counted against) the retrieved ranking.
- Mixed modality: a memory's `modality` can be `"mixed"`, each `content[]`
  entry carries its own `mimetype`, and the memory `mimetype` is that of its
  first signal.
- Per-blob content timestamps: each `content[]` entry carries `timestamp`
  (ms; 0 = unknown).
- Reference-time retrieval: keyword-only `reference_time` (aware `datetime` or
  int ms since the epoch) and `as_of` on every `process_*` call, read by
  `Retention.EPHEMERAL` calls. The `cortext_process_json_options` mirror gains
  `has_reference_ms`, `as_of` and `reference_ms`. `ReferenceTime` type alias.
- Text with caller media (`process_text_with_media[_json]`) documented and
  tested against the engine: empty media stores the canonical text, and a
  payload counts as text only when its MIME type is `text/*`.
- LI model: the binding reassembles `AIST-87M-LI.gguf` beside the AIST model
  from shipped chunks when the models manifest declares it, downloads the
  pinned, checksummed shard on the slim PyPI path, and honors
  `CORTEXT_LI_MODEL_PATH` (`~` expanded; a missing path fails fast).
  `resolve_li_model()` reports the path the engine will load. The package
  models tree vendors the engine's LI shard and manifest entry; the next
  engine release's asset tarball must carry them too, since CI and release
  builds re-vendor `models/` from it.
- Tests: engine-v5 behavior tests skip when the loaded native predates it
  (`CORTEXT_REQUIRE_ENGINE_V5=1` turns the skip into a failure).

## 1.3.0

- First PyPI release of `augmem.cortext`, tracking engine v1.3.0.
