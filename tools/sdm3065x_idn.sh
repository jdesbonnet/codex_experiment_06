#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-}"

read_idn() {
  local dev="$1"
  printf "*IDN?\n" > "$dev"
  timeout 2 cat "$dev" 2>/dev/null | tr -d '\r'
}

if [[ -z "${DEVICE}" ]]; then
  for dev in /dev/usbtmc[1-9]*; do
    [[ -e "$dev" ]] || continue
    idn="$(read_idn "$dev" || true)"
    if [[ -n "$idn" ]]; then
      echo "$dev: $idn"
    fi
  done
  exit 0
fi

if [[ ! -e "$DEVICE" ]]; then
  echo "Device not found: $DEVICE" >&2
  exit 1
fi

read_idn "$DEVICE"
