#!/usr/bin/env bash
# Idempotent venv setup for openrig-tone-analyzer.
# First run: ~30-60 s (creates .venv, installs pinned deps).
# Subsequent runs: <1 s if requirements.txt hash is unchanged.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
STAMP="$VENV_DIR/.requirements.sha"

# Compute current requirements hash (portable: sha256sum on Linux, shasum on macOS).
if command -v sha256sum >/dev/null 2>&1; then
  CURRENT_SHA="$(sha256sum requirements.txt | awk '{print $1}')"
else
  CURRENT_SHA="$(shasum -a 256 requirements.txt | awk '{print $1}')"
fi

if [ -d "$VENV_DIR" ] && [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$CURRENT_SHA" ]; then
  exit 0
fi

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
. "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate

echo "$CURRENT_SHA" > "$STAMP"
