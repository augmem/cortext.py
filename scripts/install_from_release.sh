#!/usr/bin/env bash
# Install cortext platform wheels from a GitHub Release (PyTorch-style index).
#
# Usage:
#   ./scripts/install_from_release.sh              # version from pyproject / latest tag
#   ./scripts/install_from_release.sh v1.2.4
#   CORTEXT_PY_REPO=augmem/cortext.py ./scripts/install_from_release.sh v1.2.4
#
# Env:
#   CORTEXT_PY_REPO   GitHub owner/repo (default: augmem/cortext.py)
#   PIP               pip executable (default: python3 -m pip)
#   UV                if set to 1, use `uv pip install` instead

set -euo pipefail

REPO="${CORTEXT_PY_REPO:-augmem/cortext.py}"
TAG="${1:-}"

if [[ -z "$TAG" ]]; then
  # Prefer pyproject version when run from a checkout
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  if [[ -f "$ROOT/pyproject.toml" ]]; then
    VER="$(python3 -c "import re,pathlib; t=pathlib.Path('$ROOT/pyproject.toml').read_text(); m=re.search(r'version\\s*=\\s*\\\"([^\\\"]+)\\\"', t); print(m.group(1) if m else '')")"
    if [[ -n "$VER" ]]; then
      TAG="v${VER}"
    fi
  fi
fi

if [[ -z "$TAG" ]]; then
  echo "usage: $0 vX.Y.Z" >&2
  exit 2
fi

VERSION="${TAG#v}"
BASE="https://github.com/${REPO}/releases/download/${TAG}"
INDEX="${BASE}/index.html"

echo "Installing cortext==${VERSION}"
echo "  repo:  ${REPO}"
echo "  index: ${INDEX}"

if [[ "${UV:-0}" == "1" ]] || command -v uv >/dev/null 2>&1 && [[ "${USE_UV:-1}" == "1" ]]; then
  if command -v uv >/dev/null 2>&1; then
    exec uv pip install "cortext==${VERSION}" --find-links "${INDEX}"
  fi
fi

PIP_CMD="${PIP:-python3 -m pip}"
exec ${PIP_CMD} install "cortext==${VERSION}" --find-links "${INDEX}"
