#!/usr/bin/env bash
# Serve the tiny_vm VS Code Web IDE locally. Loads the extension at
# tools/vscode/extension/ into a self-hosted VS Code Web instance via
# @vscode/test-web, with the repo root mounted as the workspace.
#
# Bind "localhost" rather than 127.0.0.1: @vscode/test-web composes the
# extension-host iframe URL as `${proto}://{{uuid}}.${host}/static/build`.
# With an IP literal, the templated host becomes "xyz.127.0.0.1" which the
# URL parser rejects ("Failed to construct 'URL': Invalid URL") and the
# extension host can't start. With a real hostname, Chrome treats
# *.localhost as loopback (RFC 6761) and everything works.
#
# This still resolves only to loopback (127.0.0.1) — no LAN exposure.
# See docs/vscode_proposal.md §1.
#
#   tools/vscode/scripts/serve.sh          # serves on 127.0.0.1:3000
#   PORT=3001 tools/vscode/scripts/serve.sh

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
EXT="$ROOT/tools/vscode/extension"
HOST="$ROOT/tools/vscode/host"
PORT_ARG=${PORT:-3000}

if [ ! -d "$HOST/node_modules" ]; then
    echo "[serve] host/node_modules missing. Run scripts/install.sh first." >&2
    exit 1
fi

if [ ! -f "$EXT/dist/web/extension.js" ]; then
    echo "[serve] extension/dist/web/extension.js missing. Building…"
    (cd "$EXT" && npm run build)
fi

# Start the compile sidecar in the background. Browser fetches from
# http://localhost:3001 by default (see extension setting tinyVm.apiUrl).
COMPILE_PORT=${COMPILE_PORT:-3001}
echo "[serve] starting compile-server on 127.0.0.1:$COMPILE_PORT"
PORT=$COMPILE_PORT HOST=127.0.0.1 REPO_ROOT="$ROOT" \
    node "$HOST/compile-server.mjs" > /tmp/compile-server.log 2>&1 &
COMPILE_PID=$!
trap "echo '[serve] stopping compile-server (pid $COMPILE_PID)'; kill $COMPILE_PID 2>/dev/null || true" EXIT INT TERM

# Give it a moment to bind.
sleep 0.3

cd "$HOST"
echo "[serve] starting @vscode/test-web on 127.0.0.1:$PORT_ARG"
echo "[serve] extension path: $EXT"
echo "[serve] workspace root: $ROOT"
# --browser=none: just serve the static IDE; the user opens their own browser.
#   Avoids @vscode/test-web's Playwright dependency at runtime, which is
#   broken on ubuntu26.04-x64 (no bundled Chromium for that platform).
# --quality=stable: avoids Insiders/Stable workbench-renaming churn.
#
# We deliberately do NOT pass --coi. With @vscode/test-web 0.0.80 + current
# VS Code Stable, --coi breaks the Web Worker extension host iframe URL
# construction (TypeError: Failed to construct 'URL' in
# webWorkerExtensionHost.ts), which cascades into "no FS provider for
# vscode-test-web://mount/" and an empty workspace. We do not need
# SharedArrayBuffer for the v1 sim; if/when we do, we will configure the
# iframe endpoint properly rather than just flipping --coi back on.
exec npx vscode-test-web \
    --browser=none \
    --quality=stable \
    --extensionDevelopmentPath="$EXT" \
    --port="$PORT_ARG" \
    --host=localhost \
    "$ROOT"
