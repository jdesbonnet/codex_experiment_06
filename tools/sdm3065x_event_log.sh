#!/usr/bin/env bash
set -euo pipefail

UART_DEV="/dev/ttyACM0"
USB_DEV="/dev/usbtmc0"
OUT_FILE="/tmp/current_events.csv"
MODE="dc"

usage() {
  cat <<'EOF'
Usage: sdm3065x_event_log.sh [--uart /dev/ttyACM0] [--usb /dev/usbtmc0]
                             [--out /path/to/log.csv] [--mode dc|ac]
Listens for UART messages and logs a current sample on key events.
Events (from sleep_wake): "Sleep: entering deep-sleep", "Sleep: awake again".
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --uart) UART_DEV="$2"; shift 2 ;;
    --usb) USB_DEV="$2"; shift 2 ;;
    --out) OUT_FILE="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ ! -e "$UART_DEV" ]]; then
  echo "UART device not found: $UART_DEV" >&2
  exit 1
fi
if [[ ! -e "$USB_DEV" ]]; then
  echo "USBTMC device not found: $USB_DEV" >&2
  exit 1
fi

mode_uc="$(echo "$MODE" | tr '[:lower:]' '[:upper:]')"
if [[ "$mode_uc" != "DC" && "$mode_uc" != "AC" ]]; then
  echo "Invalid --mode: $MODE (use dc or ac)" >&2
  exit 1
fi

if [[ ! -e "$OUT_FILE" ]]; then
  echo "timestamp_utc,event,value" >> "$OUT_FILE"
fi

measure_current() {
  local value=""
  printf "MEAS:CURR:%s?\n" "$mode_uc" > "$USB_DEV"
  sleep 0.05
  value="$(timeout 2 cat "$USB_DEV" 2>/dev/null | tr -d '\r' | head -n1)"
  if [[ -z "$value" ]]; then
    printf "MEAS:CURR:%s?\n" "$mode_uc" > "$USB_DEV"
    sleep 0.05
    value="$(timeout 2 cat "$USB_DEV" 2>/dev/null | tr -d '\r' | head -n1)"
  fi
  echo "$value"
}

stty -F "$UART_DEV" 57600 -crtscts -ixon -ixoff raw -echo

stdbuf -oL cat "$UART_DEV" | while IFS= read -r line; do
  event=""
  if [[ "$line" == *"Sleep: entering deep-sleep"* ]]; then
    event="enter_sleep"
  elif [[ "$line" == *"Sleep: awake again"* ]]; then
    event="wake"
  elif [[ "$line" == *"Sleep: starting"* ]]; then
    event="start"
  fi

  if [[ -n "$event" ]]; then
    ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    value="$(measure_current)"
    if [[ -z "$value" ]]; then
      value="NaN"
    fi
    echo "${ts},${event},${value}" >> "$OUT_FILE"
  fi
done
