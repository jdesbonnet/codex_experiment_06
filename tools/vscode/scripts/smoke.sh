#!/usr/bin/env bash
# End-to-end smoke for the VS Code Web tiny_vm dev environment.
#
# Verifies, in order:
#   1. Rust wasm sim — `cargo test` covers the opcode-level unit tests
#      plus the regression suite that runs every projects/tiny_vm/tests/*
#      program through the wasm sim and asserts parity with the hardware
#      regression's expected_lines().
#   2. Extension typecheck and bundle.
#   3. compile-server /api/health (started by Playwright via serve.sh
#      reuseExistingServer; checked through curl as an explicit signal).
#   4. Playwright e2e — the M4 spec drives VS Code Web end-to-end:
#      open blink.cvm.c, compile via the sidecar, launch DAP, step
#      through the loop, stop the session.
#
# This is the script CI / a new contributor runs before merging anything
# under tools/vscode/. Mirrors tools/theia/scripts/smoke.sh for
# the Theia version.
#
# Usage:
#   tools/vscode/scripts/smoke.sh

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
WEB="$ROOT/tools/vscode"

log()  { echo "[smoke] $*"; }
fail() { echo "[smoke][error] $*" >&2; exit 1; }

# --- 1. Rust wasm sim ------------------------------------------------------
if command -v cargo >/dev/null 2>&1; then
    log "step 1/4: cargo test (sim)"
    (cd "$WEB/sim/rust" && cargo test --quiet)
elif [ -f "$HOME/.cargo/env" ]; then
    log "step 1/4: cargo test (sim, sourcing ~/.cargo/env)"
    # shellcheck source=/dev/null
    . "$HOME/.cargo/env"
    (cd "$WEB/sim/rust" && cargo test --quiet)
else
    log "step 1/4: cargo not found, skipping cargo test"
    log "         (the committed sim/pkg/ stands in; reinstall Rust to verify parity)"
fi

# --- 2. Extension typecheck + build ---------------------------------------
log "step 2/4: extension typecheck + build"
(cd "$WEB/extension" && npm run --silent typecheck && npm run --silent build)
[ -s "$WEB/extension/dist/web/extension.js" ] || fail "extension bundle not produced"

# --- 3. compile-server health --------------------------------------------
# Playwright's webServer config starts serve.sh on demand (which in turn
# spawns compile-server), so we don't need to manage it directly here.
# Probe ahead of the e2e so a server-side failure has a clearer error
# than a Playwright timeout.
COMPILE_PORT=${COMPILE_PORT:-3001}
log "step 3/4: compile-server reachability (will start serve.sh if needed)"
if ! curl -sf -m 2 "http://127.0.0.1:$COMPILE_PORT/api/health" >/dev/null; then
    log "         starting serve.sh in the background"
    "$WEB/scripts/serve.sh" > /tmp/smoke-serve.log 2>&1 &
    SERVE_PID=$!
    trap 'kill $SERVE_PID 2>/dev/null || true' EXIT INT TERM
    # Wait up to 60s for both ports to come up. First boot includes the
    # @vscode/test-web download (~50 MB) which can be slow.
    for _ in $(seq 1 60); do
        if curl -sf -m 1 "http://127.0.0.1:$COMPILE_PORT/api/health" >/dev/null \
           && curl -sf -m 1 "http://127.0.0.1:3000/" >/dev/null; then
            break
        fi
        sleep 1
    done
fi
curl -sf -m 5 "http://127.0.0.1:$COMPILE_PORT/api/health" >/dev/null \
    || fail "compile-server not reachable at :$COMPILE_PORT — see /tmp/smoke-serve.log and /tmp/compile-server.log"

# --- 4. Playwright e2e ----------------------------------------------------
log "step 4/4: playwright e2e (blink-debug.spec.ts)"
(cd "$WEB/e2e" && npx --no-install playwright test --project=chrome-system --reporter=list)

log "smoke: OK"
