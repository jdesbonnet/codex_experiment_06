#!/usr/bin/env bash
# Start the tiny_vm IDE (Theia browser app).
#
# Usage:
#   tools/dev_env/scripts/serve.sh            # listens on 0.0.0.0:3000
#   PORT=3001 tools/dev_env/scripts/serve.sh

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
THEIA_DIR="$ROOT/tools/dev_env/theia"
PORT_ARG=${PORT:-3000}

if [ ! -d "$THEIA_DIR/node_modules" ]; then
    echo "[serve] tools/dev_env/theia/node_modules missing. Run scripts/install.sh first." >&2
    exit 1
fi

cd "$THEIA_DIR/browser-app"
echo "[serve] starting Theia on 0.0.0.0:$PORT_ARG ..."
exec npx theia start --hostname 0.0.0.0 --port "$PORT_ARG"
