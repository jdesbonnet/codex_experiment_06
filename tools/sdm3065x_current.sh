#!/usr/bin/env bash
set -euo pipefail

DEVICE=""
MODE="dc"
RANGE=""
COUNT=1
INTERVAL_S=1
LOG_FILE=""
LOG_FORMAT="csv"

usage() {
  cat <<'EOF'
Usage: sdm3065x_current.sh [--device /dev/usbtmcX] [--mode dc|ac] [--range AUTO|<value>]
                           [--count N] [--interval SEC] [--log FILE] [--format csv|plain]
Examples:
  sdm3065x_current.sh --device /dev/usbtmc1
  sdm3065x_current.sh --device /dev/usbtmc1 --mode dc --range AUTO --count 10 --interval 0.5
  sdm3065x_current.sh --device /dev/usbtmc1 --count 60 --interval 1 --log /tmp/current.csv --format csv
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device) DEVICE="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --range) RANGE="$2"; shift 2 ;;
    --count) COUNT="$2"; shift 2 ;;
    --interval) INTERVAL_S="$2"; shift 2 ;;
    --log) LOG_FILE="$2"; shift 2 ;;
    --format) LOG_FORMAT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$DEVICE" ]]; then
  echo "Missing --device. Example: --device /dev/usbtmc1" >&2
  exit 1
fi

if [[ ! -e "$DEVICE" ]]; then
  echo "Device not found: $DEVICE" >&2
  exit 1
fi

mode_uc="$(echo "$MODE" | tr '[:lower:]' '[:upper:]')"
if [[ "$mode_uc" != "DC" && "$mode_uc" != "AC" ]]; then
  echo "Invalid --mode: $MODE (use dc or ac)" >&2
  exit 1
fi

if [[ -n "$RANGE" ]]; then
  cmd="MEAS:CURR:${mode_uc}? ${RANGE}"
else
  cmd="MEAS:CURR:${mode_uc}?"
fi

if [[ -n "$LOG_FILE" && "$LOG_FORMAT" == "csv" ]]; then
  if [[ ! -e "$LOG_FILE" ]]; then
    echo "timestamp_utc,value" >> "$LOG_FILE"
  fi
fi

read_value() {
  local dev="$1"
  printf "%s\n" "$cmd" > "$dev"
  sleep 0.05
  timeout 2 cat "$dev" 2>/dev/null | tr -d '\r' | head -n1
}

for ((i = 0; i < COUNT; i++)); do
  value="$(read_value "$DEVICE")"
  if [[ -z "$value" ]]; then
    value="$(read_value "$DEVICE")"
  fi
  if [[ -z "$value" ]]; then
    echo "ERROR: no response from device" >&2
    exit 1
  fi

  echo "$value"
  if [[ -n "$LOG_FILE" ]]; then
    ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    if [[ "$LOG_FORMAT" == "csv" ]]; then
      echo "${ts},${value}" >> "$LOG_FILE"
    else
      echo "${ts} ${value}" >> "$LOG_FILE"
    fi
  fi
  if [[ $i -lt $((COUNT - 1)) ]]; then
    sleep "$INTERVAL_S"
  fi
done
