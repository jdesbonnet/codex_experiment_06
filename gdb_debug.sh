#!/usr/bin/env bash
set -euo pipefail

ELF=${1:-build/lpc1114_min.elf}
GDB_BIN=${GDB_BIN:-gdb-multiarch}
GDB_PORT=${GDB_PORT:-3333}

if [ ! -f "${ELF}" ]; then
  echo "ELF not found: ${ELF}" >&2
  exit 2
fi

"${GDB_BIN}" \
  -ex "set pagination off" \
  -ex "target extended-remote :${GDB_PORT}" \
  -ex "monitor reset halt" \
  -ex "load" \
  -ex "monitor reset halt" \
  -ex "break main" \
  -ex "continue" \
  "${ELF}"
