#!/usr/bin/env bash
set -euo pipefail

OPENOCD_SCRIPTS="${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}"
PULSE_MS="${1:-200}"

if ! [[ "$PULSE_MS" =~ ^[0-9]+$ ]]; then
  echo "Usage: $0 [pulse_ms]" >&2
  exit 2
fi

openocd -s "$OPENOCD_SCRIPTS" -f interface/cmsis-dap.cfg \
  -c "transport select swd; reset_config srst_only srst_open_drain connect_deassert_srst; init; adapter assert srst; sleep ${PULSE_MS}; adapter deassert srst; shutdown"
