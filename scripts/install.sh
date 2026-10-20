#!/usr/bin/env bash
# Curl-friendly entrypoint for release installs (uploaded as a release asset).
# Usage: curl -fsSL …/install.sh | bash -s -- v2.0.0
set -euo pipefail
TAG="${1:-v2.0.0}"
REPO="${CORTEXT_PY_REPO:-augmem/cortext.py}"
VERSION="${TAG#v}"
BASE="https://github.com/${REPO}/releases/download/${TAG}"
INDEX="${BASE}/index.html"
echo "Installing augmem.cortext==${VERSION} from ${INDEX}"
if command -v uv >/dev/null 2>&1; then
  exec uv pip install "augmem.cortext==${VERSION}" --find-links "${INDEX}"
fi
exec python3 -m pip install "augmem.cortext==${VERSION}" --find-links "${INDEX}"
