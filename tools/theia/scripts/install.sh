#!/usr/bin/env bash
# Install dependencies for the tiny_vm development environment.
#
# Verifies host requirements (python3, node, npm), then runs
# `npm install` in tools/theia/theia/ which is the Theia workspace root.
#
# Usage:
#   tools/theia/scripts/install.sh

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
THEIA_DIR="$ROOT/tools/theia/theia"

log()  { echo "[install] $*"; }
fail() { echo "[install][error] $*" >&2; exit 1; }

# ---- python ----------------------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 not found; vm_cc.py, the sim, and the DAP server all need it"
fi
PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log "python3 $PYV"

# ---- node + npm ------------------------------------------------------------

if ! command -v node >/dev/null 2>&1; then
    fail "node not found; install Node.js 18+ (Theia needs it)"
fi
NODEV=$(node --version | sed 's/^v//')
NODEMAJ=${NODEV%%.*}
if [ "$NODEMAJ" -lt 18 ]; then
    fail "node $NODEV is too old; Theia requires Node 18+"
fi
log "node $NODEV"

if ! command -v npm >/dev/null 2>&1; then
    fail "npm not found"
fi
log "npm $(npm --version)"

# ---- workspace install -----------------------------------------------------

log "installing Theia workspace deps in $THEIA_DIR (this is the slow step)..."
( cd "$THEIA_DIR" && npm install --no-audit --no-fund --loglevel=error )

log "building Theia browser app..."
( cd "$THEIA_DIR" && npm run build )

log "done. Start the IDE with: tools/theia/scripts/serve.sh"
