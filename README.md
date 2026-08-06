# cortext.py

Turnkey pure-Python (ctypes) bindings for [Cortext](https://github.com/augmem/cortext).

**Distribution model (PyTorch-style):** large platform wheels are published on
**GitHub Releases**, not pypi.org. Each wheel ships one OS/arch native plus the
AIST model chunks — install is offline after the wheel download.

## Install (GitHub Releases wheelhouse)

```bash
# Replace version as needed
export CORTEXT_VERSION=1.2.4
export CORTEXT_INDEX="https://github.com/augmem/cortext.py/releases/download/v${CORTEXT_VERSION}/index.html"

pip install "cortext==${CORTEXT_VERSION}" --find-links "${CORTEXT_INDEX}"
# or
uv pip install "cortext==${CORTEXT_VERSION}" --find-links "${CORTEXT_INDEX}"

# one-liner
curl -fsSL "https://github.com/augmem/cortext.py/releases/download/v${CORTEXT_VERSION}/install.sh" \
  | bash -s -- "v${CORTEXT_VERSION}"
```

Pip/uv selects the matching `py3-none-<platform>` wheel automatically.

### Private / mirror simple index (optional)

GitHub Releases are flat files, so a live `…/simple/cortext/` URL is not
available on the release itself. Each release includes `simple-index.tar.gz`
(PEP 503 layout with absolute wheel URLs) for hosting on Pages, S3, or an
internal index:

```bash
tar -xzf simple-index.tar.gz
# serve the extracted simple/ directory, then:
pip install cortext==1.2.4 --index-url https://your-mirror.example/simple/
```

### Local wheelhouse / editable checkout

```bash
# After scripts/build_wheels.py
pip install cortext==1.2.4 --find-links dist/wheels --no-index

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
`media_mimetype` to `process_text_with_media`.

Python 3.10+. Binding **1.2.4** tracks engine **v1.2.4**.

## Why not pypi.org?

Default PyPI limits are **~100 MB per file**. Each platform wheel is ~250 MiB
(native with embedded model + model chunks). PyTorch solves this with a
secondary index (`download.pytorch.org`); we use **GitHub Release assets** the
same way.

| Channel | Contents |
| --- | --- |
| GitHub Release `vX.Y.Z` | Six platform wheels + `index.html` + `install.sh` |
| pypi.org | Not used for fat wheels (limit) |
| git checkout | Sources + model chunks; **natives vendored in CI** (files are ~140 MiB and exceed GitHub’s git limit) |

Local full tree after clone:

```bash
python3 scripts/vendor_release_assets.py --from-release v1.2.4 --force
uv sync && uv run pytest -q
```

## What each wheel ships

```text
cortext/
  native/<this-platform-only>/libcortext.* | cortext.dll
  models/   # AIST chunks + vocab + manifest
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
| 1 | `CORTEXT_LIBRARY_PATH` / `CORTEXT_AIST_MODEL_PATH` |
| 2 | `CORTEXT_ASSETS_DIR` |
| 3 | Shipped package `native/` + `models/` (the wheel contents) |

No sibling checkouts and no runtime GitHub download on the happy path.

## Environment (optional)

| Variable | Role |
| --- | --- |
| `CORTEXT_LIBRARY_PATH` | Override shared library |
| `CORTEXT_ASSETS_DIR` | Override entire assets root |
| `CORTEXT_AIST_MODEL_PATH` | Full `.gguf` (skip materialize) |
| `CORTEXT_MODEL_CACHE_DIR` | Materialize cache directory |

## Maintainer release flow

```bash
# 1) Vendor engine assets (or rely on CI to fetch augmem/cortext release)
python3 scripts/vendor_release_assets.py --from-release v1.2.4 --force

# 2) Build platform wheels + local indexes
python3 scripts/build_wheels.py

# 3) Tag + push — CI (.github/workflows/release-wheels.yml) builds, writes
#    absolute-URL indexes, and uploads everything to the GitHub Release
git tag v1.2.4
git push origin v1.2.4
```

Manual publish of an existing wheelhouse:

```bash
BASE="https://github.com/augmem/cortext.py/releases/download/v1.2.4"
python3 scripts/write_wheel_index.py dist/wheels --version 1.2.4 --base-url "$BASE"
gh release create v1.2.4 dist/wheels/*.whl dist/wheels/index.html \
  dist/wheels/install.sh dist/wheels/INSTALL.md \
  --title "cortext.py 1.2.4" --notes-file dist/wheels/INSTALL.md
```

## API

- `Config`, `Media`, `Retention`, `Cortext`, `CortextError`
- `version()`, `last_error()`, `load_library()`, `package_assets_ready()`
- `process_*` / `embed_*` / `consolidate` / `flush` / `reset`
- `materialize_model`, `resolve_aist_model`

## Develop / test

```bash
uv sync
uv run pytest -q
```
