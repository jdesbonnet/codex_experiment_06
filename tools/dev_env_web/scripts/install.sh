#!/usr/bin/env bash
# Install npm deps for the VS Code Web dev environment.
#
# Verifies Node and rust toolchain, runs `npm install` in both extension/
# and host/, then builds the extension once so serve.sh can start cleanly.
#
# Usage:
#   tools/dev_env_web/scripts/install.sh

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
WEB="$ROOT/tools/dev_env_web"

log()  { echo "[install] $*"; }
fail() { echo "[install][error] $*" >&2; exit 1; }

# ---- node + npm ------------------------------------------------------------
if ! command -v node >/dev/null 2>&1; then
    fail "node not found; install Node.js 18+"
fi
log "node $(node --version)"
if ! command -v npm >/dev/null 2>&1; then
    fail "npm not found"
fi

# ---- extension -------------------------------------------------------------
log "installing extension/"
(cd "$WEB/extension" && npm install --no-audit --no-fund)
log "building extension/"
(cd "$WEB/extension" && npm run build)

# ---- host ------------------------------------------------------------------
log "installing host/"
(cd "$WEB/host" && npm install --no-audit --no-fund)

# ---- rust sim (optional, for cargo test) ----------------------------------
if [ -f "$HOME/.cargo/env" ]; then
    # shellcheck source=/dev/null
    . "$HOME/.cargo/env"
fi
if command -v cargo >/dev/null 2>&1 && command -v wasm-pack >/dev/null 2>&1; then
    log "rust + wasm-pack present — rebuilding sim/pkg/ for parity"
    (cd "$WEB/sim/rust" && wasm-pack build --release --target web --out-dir ../pkg)
else
    log "rust or wasm-pack missing — skipping sim rebuild (the committed pkg/ stands in)"
fi

log "done. Next: tools/dev_env_web/scripts/serve.sh"
