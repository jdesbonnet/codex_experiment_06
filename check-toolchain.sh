#!/usr/bin/env bash
set -euo pipefail

missing=0

check_cmd() {
  local name=$1
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "missing: $name"
    missing=1
  else
    echo "found: $name -> $(command -v "$name")"
    "$name" --version | head -n 1
  fi
}

check_cmd arm-none-eabi-gcc
check_cmd arm-none-eabi-objcopy
check_cmd arm-none-eabi-size
check_cmd gdb-multiarch
check_cmd openocd

if ! command -v arm-none-eabi-gdb >/dev/null 2>&1; then
  echo "note: arm-none-eabi-gdb not found; gdb-multiarch will be used instead"
else
  echo "found: arm-none-eabi-gdb -> $(command -v arm-none-eabi-gdb)"
  arm-none-eabi-gdb --version | head -n 1
fi

if [ $missing -ne 0 ]; then
  echo "one or more required tools are missing"
  exit 1
fi

exit 0
