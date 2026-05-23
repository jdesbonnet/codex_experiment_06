#!/usr/bin/env bash
# Wrapper for console-capture.mjs that resolves playwright-core from
# tools/dev_env_web/host/node_modules. Run from anywhere.
#
#   tools/dev_env_web/scripts/console-capture.sh                 # default URL
#   tools/dev_env_web/scripts/console-capture.sh http://host/    # custom URL
#   WAIT_MS=10000 tools/dev_env_web/scripts/console-capture.sh
#   FILTER='tiny-vm|extension|grammar' tools/dev_env_web/scripts/console-capture.sh

set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
exec node "$ROOT/tools/dev_env_web/host/console-capture.mjs" "$@"
