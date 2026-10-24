#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  bash scripts/install-macos.sh
fi
exec .venv/bin/python -m mailord --demo --open "$@"
