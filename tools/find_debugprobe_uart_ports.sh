#!/usr/bin/env bash
set -euo pipefail

# Detect Raspberry Pi debugprobe CDC ACM UART endpoints.
# With dual-CDC firmware, one interface is primary R/W and one is mirror RX-only.

MODE="human"
if [[ "${1:-}" == "--env" ]]; then
  MODE="env"
fi

find_tty_for_interface() {
  local want="$1"
  local tty
  for path in /sys/class/tty/ttyACM*; do
    [[ -e "$path" ]] || continue
    tty="$(basename "$path")"
    local iface_file="$path/device/interface"
    if [[ -r "$iface_file" ]] && grep -Fq "$want" "$iface_file"; then
      echo "/dev/$tty"
      return 0
    fi
  done
  return 1
}

PRIMARY=""
MIRROR=""

if PRIMARY="$(find_tty_for_interface 'CDC-ACM UART Interface' 2>/dev/null)"; then
  :
else
  PRIMARY=""
fi

if MIRROR="$(find_tty_for_interface 'CDC-ACM UART Mirror' 2>/dev/null)"; then
  :
else
  MIRROR=""
fi

if [[ "$MODE" == "env" ]]; then
  echo "DEBUGPROBE_UART_PRIMARY=${PRIMARY}"
  echo "DEBUGPROBE_UART_MIRROR=${MIRROR}"
  exit 0
fi

echo "Debugprobe UART port mapping:"
echo "  primary: ${PRIMARY:-not found}"
echo "  mirror : ${MIRROR:-not found}"

if [[ -z "$PRIMARY" && -z "$MIRROR" ]]; then
  echo "No matching dual-CDC interfaces found."
  echo "Tip: check 'ls /dev/ttyACM*' and inspect '/sys/class/tty/ttyACMx/device/interface'."
fi
