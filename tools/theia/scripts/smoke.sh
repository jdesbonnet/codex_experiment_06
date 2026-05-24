#!/usr/bin/env bash
# End-to-end smoke test for the tiny_vm dev environment.
#
# Verifies:
#   1. vm_cc.py compiles count10.cvm.c with --map.
#   2. The host-side simulator runs the binary and produces 1..10.
#   3. The DAP server accepts a launch request, runs to halt, and emits
#      'output' events matching 1..10.
#
# This is the script CI / new contributors run before merging anything.
#
# Usage:
#   tools/theia/scripts/smoke.sh

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$ROOT"

log() { echo "[smoke] $*"; }
fail() { echo "[smoke][error] $*" >&2; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

SRC="$ROOT/projects/tiny_vm/tests/count10.cvm.c"
BIN="$WORK/count10.bin"
MAP="$BIN.map"
EXPECTED=$'1\n2\n3\n4\n5\n6\n7\n8\n9\n10'

log "step 1/4: compile $SRC --map"
./tools/vm_cc.py "$SRC" -o "$BIN" --map >/dev/null
[ -s "$BIN" ] || fail "bytecode is empty"
[ -s "$MAP" ] || fail "map sidecar is empty"

log "step 2/4: host-side sim cli"
GOT=$(./tools/theia/sim/cli.py "$BIN" | tr -d '\r')
if [ "$GOT" != "$EXPECTED" ]; then
    fail "sim output mismatch.\nexpected:\n$EXPECTED\n---\ngot:\n$GOT"
fi

log "step 3/4: vm tool tests"
python3 tools/test_vm_tools.py >/dev/null

log "step 4/4: dap server end-to-end"
python3 tools/theia/dap/test_dap.py >/dev/null

log "smoke: OK"
