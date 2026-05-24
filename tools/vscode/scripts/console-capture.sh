#!/usr/bin/env bash
# Wrapper for console-capture.mjs that resolves playwright-core from
# tools/vscode/host/node_modules. Run from anywhere.
#
#   tools/vscode/scripts/console-capture.sh                 # default URL
#   tools/vscode/scripts/console-capture.sh http://host/    # custom URL
#   WAIT_MS=10000 tools/vscode/scripts/console-capture.sh
#   FILTER='tiny-vm|extension|grammar' tools/vscode/scripts/console-capture.sh

set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
exec node "$ROOT/tools/vscode/host/console-capture.mjs" "$@"
