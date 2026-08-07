#!/usr/bin/env bash
# Curl-friendly entrypoint for release installs (uploaded as a release asset).
# Usage: curl -fsSL …/install.sh | bash -s -- v1.3.0
set -euo pipefail
TAG="${1:-v1.3.0}"
REPO="${CORTEXT_PY_REPO:-augmem/cortext.py}"
VERSION="${TAG#v}"
BASE="https://github.com/${REPO}/releases/download/${TAG}"
INDEX="${BASE}/index.html"
echo "Installing cortext==${VERSION} from ${INDEX}"
if command -v uv >/dev/null 2>&1; then
  exec uv pip install "cortext==${VERSION}" --find-links "${INDEX}"
fi
exec python3 -m pip install "cortext==${VERSION}" --find-links "${INDEX}"
