# cortext.py

Turnkey pure-Python (ctypes) bindings for [Cortext](https://github.com/augmem/cortext).

The `augmem.cortext` PyPI package contains all six thin platform natives and
downloads the pinned AIST model on first engine creation. Full offline wheels
with embedded model chunks remain available on GitHub Releases.

## Install from PyPI

```bash
pip install augmem.cortext==1.3.0
# or
uv pip install augmem.cortext==1.3.0
```

The first `Cortext` instance downloads and verifies the AIST model, its
late-interaction reranker (`AIST-87M-LI.gguf`, placed beside the model) and the
tokenizer. Set `CORTEXT_AIST_MODEL_PATH` to an existing GGUF for offline use,
with `AIST-87M-LI.gguf` in the same directory or `CORTEXT_LI_MODEL_PATH` set.

## Install (GitHub Releases wheelhouse)

```bash
# Replace version as needed
export CORTEXT_VERSION=1.3.0
export CORTEXT_INDEX="https://github.com/augmem/cortext.py/releases/download/v${CORTEXT_VERSION}/index.html"

pip install "augmem.cortext==${CORTEXT_VERSION}" --find-links "${CORTEXT_INDEX}"
# or
uv pip install "augmem.cortext==${CORTEXT_VERSION}" --find-links "${CORTEXT_INDEX}"

# one-liner
curl -fsSL "https://github.com/augmem/cortext.py/releases/download/v${CORTEXT_VERSION}/install.sh" \
  | bash -s -- "v${CORTEXT_VERSION}"
```

Pip/uv selects the matching `py3-none-<platform>` wheel automatically.

### Private / mirror simple index (optional)

GitHub Releases are flat files, so a live `…/simple/augmem-cortext/` URL is not
available on the release itself. Each release includes `simple-index.tar.gz`
(PEP 503 layout with absolute wheel URLs) for hosting on Pages, S3, or an
internal index:

```bash
tar -xzf simple-index.tar.gz
# serve the extracted simple/ directory, then:
pip install augmem.cortext==1.3.0 --index-url https://your-mirror.example/simple/
```

### Local wheelhouse / editable checkout

```bash
# After scripts/build_wheels.py
pip install augmem.cortext==1.3.0 --find-links dist/wheels --no-index

# Dev monorepo (all six natives in-tree)
uv sync
pip install -e .
```

```python
import cortext

print(cortext.version())

with cortext.Cortext(":memory:") as memory:
    ctx = memory.process_text("Bailey likes tennis balls.", "chat/main")
    emb = memory.embed_text("embed without storing")
    print(len(emb))
```

For binary attachments, pass `Media(data, mimetype)` or raw bytes with
`media_mimetype` to `process_text_with_media` (or the audio / image
`*_with_media` variants). The text is still what gets encoded; the media bytes
are what the memory stores, under their MIME type. Empty media stores the
canonical text. A payload is treated as text (keyword index, standing
directives, evidence charged by its bytes) only when its MIME type is `text/*`.

```python
memory.process_text_with_media(
    "Boarding pass for the ferry, gate B12.", "chat/pass",
    cortext.Media(pdf_bytes, "application/pdf"),
)
```

A query context leads with `standing_memory` (standing directives such as
"Always ...", outside the retrieved ranking; show it ahead of
`retrieved_memory` and do not count it against a cut of the retrieved list),
then `retrieved_memory`.

Every `process_*` call takes `evidence_budget_bytes`: `None` (default) returns
recalled memories whole (there is no per-memory size cap); a positive byte count fits `standing_memory` plus
`retrieved_memory` (with attached neighbours) within it, text counted by its
UTF-8 bytes and other payloads as 480 bytes each. Grouped memories keep their
members most similar to the query, and more distinct memories are kept
trimmed before lower-ranked ones are left out. Convert a token budget with
your reader's tokenizer rate (8,000 tokens at 4.35 chars/token is 34,800).

```python
ctx = memory.process_text(
    "When is the marathon long run?", "query/main",
    retention=cortext.Retention.EPHEMERAL, evidence_budget_bytes=34_800,
)
evidence = ctx["standing_memory"] + ctx["retrieved_memory"]
```

A query (`Retention.EPHEMERAL`) call also takes a reference time: keyword-only
`reference_time`, an aware `datetime` or an `int` of milliseconds since the
Unix epoch (past or future), and `as_of`. Unset, retrieval is unchanged. Set,
the long-term memories nearest that time join the candidates; nothing is
dropped for being later. With `as_of=True`, memories that start after the
reference time are hidden ("what did I know then?"). `as_of` needs
`reference_time`; naive datetimes are rejected. Other retentions ignore both.

```python
from datetime import datetime, timezone

ctx = memory.process_text(
    "Where was I staying?", "query/main",
    retention=cortext.Retention.EPHEMERAL,
    reference_time=datetime(2026, 3, 1, tzinfo=timezone.utc), as_of=True,
)
```

Each memory in `standing_memory` / `retrieved_memory` / `working_memory` carries `content`: every
signal payload of the memory as `{size_bytes, mimetype, base64, timestamp}`, in
signal order, where `timestamp` is that payload's time in ms (0 = unknown).
`modality` is the modality its signals share, or `"mixed"` when they
differ (for example a turn's text and the photo sent with it under one source);
the memory's own `mimetype` is that of its first signal.

Python 3.10+. Binding **1.3.0** tracks engine **v1.3.0**. The standing
memory block, evidence budget, mixed memories, per-content timestamps and
reference time need a native built from cortext.cpp `main` until the next
engine release (point `CORTEXT_LIBRARY_PATH` at it); see `CHANGELOG.md`.

## Distribution channels

Default PyPI limits are **~100 MB per file**. The PyPI wheel stays below that
limit by shipping thin natives and fetching the verified model on first use.
GitHub Release wheels are larger but work offline after download.

| Channel | Contents |
| --- | --- |
| GitHub Release `vX.Y.Z` | Six platform wheels + `index.html` + `install.sh` |
| pypi.org | Slim wheel + verified first-use model bootstrap |
| git checkout | Sources + model chunks; **natives vendored in CI** (files are ~140 MiB and exceed GitHub’s git limit) |

Local full tree after clone:

```bash
python3 scripts/vendor_release_assets.py --from-release v1.3.0 --force
uv sync && uv run pytest -q
```

## What each wheel ships

```text
cortext/
  native/<this-platform-only>/libcortext.* | cortext.dll
  models/   # AIST chunks + vocab + manifest (GitHub Release wheel only)
  *.py      # ctypes binding
```

| Package tag | Wheel platform tag |
| --- | --- |
| `linux-x86_64` | `manylinux_2_17_x86_64` / `manylinux2014_x86_64` |
| `linux-aarch64` | `manylinux_2_17_aarch64` / `manylinux2014_aarch64` |
| `macos-x86_64` | `macosx_11_0_x86_64` |
| `macos-aarch64` | `macosx_11_0_arm64` |
| `windows-x86_64` | `win_amd64` |
| `windows-aarch64` | `win_arm64` |

## Resolution at runtime

| Priority | Source |
| --- | --- |
| 1 | `CORTEXT_LIBRARY_PATH` / `CORTEXT_AIST_MODEL_PATH` / `CORTEXT_LI_MODEL_PATH` |
| 2 | `CORTEXT_ASSETS_DIR` |
| 3 | Shipped package `native/` + `models/` (GitHub Release wheel) or verified model cache (PyPI wheel) |

No sibling checkouts are searched. The PyPI wheel downloads only its pinned
model assets when no explicit model path is provided.

The late-interaction reranker resolves the way the engine looks for it:
`CORTEXT_LI_MODEL_PATH`, else `AIST-87M-LI.gguf` beside the AIST model (the
binding reassembles it there from the shipped chunks when the models manifest
declares it, or downloads it on the PyPI path), else a reranker linked into the
native library. `resolve_li_model()` returns the path the engine will load,
looking beside `CORTEXT_AIST_MODEL_PATH` when that names a file (otherwise it
resolves the packaged model first, which may reassemble or download it). A
`~` in `CORTEXT_LI_MODEL_PATH` is expanded before the engine sees it.

## Environment (optional)

| Variable | Role |
| --- | --- |
| `CORTEXT_LIBRARY_PATH` | Override shared library |
| `CORTEXT_ASSETS_DIR` | Override entire assets root |
| `CORTEXT_AIST_MODEL_PATH` | Full `.gguf` (skip materialize) |
| `CORTEXT_LI_MODEL_PATH` | Late-interaction reranker `.gguf` (must exist when set) |
| `CORTEXT_MODEL_CACHE_DIR` | Materialize cache directory |

## Maintainer release flow

```bash
# 1) Vendor engine assets (or rely on CI to fetch augmem/cortext release)
python3 scripts/vendor_release_assets.py --from-release v1.3.0 --force

# 2) Build platform wheels + local indexes
python3 scripts/build_wheels.py

# 3) Build the PyPI package from thin natives
python3 scripts/build_pypi.py --native-root /path/to/cortext-thin-v1.3-build

# 4) Tag + push — CI (.github/workflows/release-wheels.yml) builds, writes
#    absolute-URL indexes, and uploads everything to the GitHub Release
git tag v1.3.0
git push origin v1.3.0

# 5) Upload dist/pypi/* to PyPI with a configured API token
```

Manual publish of an existing wheelhouse:

```bash
BASE="https://github.com/augmem/cortext.py/releases/download/v1.3.0"
python3 scripts/write_wheel_index.py dist/wheels --version 1.3.0 --base-url "$BASE"
gh release create v1.3.0 dist/wheels/*.whl dist/wheels/index.html \
  dist/wheels/install.sh dist/wheels/INSTALL.md \
  --title "cortext.py 1.3.0" --notes-file dist/wheels/INSTALL.md
```

## API

- `Config`, `Media`, `Retention`, `ReferenceTime`, `Cortext`, `CortextError`
- `version()`, `last_error()`, `load_library()`, `package_assets_ready()`
- `process_*` / `embed_*` / `consolidate` / `flush` / `reset`
- `materialize_model`, `resolve_aist_model`, `resolve_li_model`

## Develop / test

```bash
uv sync
uv run pytest -q

# Against a locally built engine (engine-v5 tests skip on older natives;
# CORTEXT_REQUIRE_ENGINE_V5=1 makes that a failure)
CORTEXT_REQUIRE_ENGINE_V5=1 \
CORTEXT_LIBRARY_PATH=/path/to/libcortext.dylib \
CORTEXT_LI_MODEL_PATH=/path/to/AIST-87M-LI.gguf \
uv run pytest -q
```
