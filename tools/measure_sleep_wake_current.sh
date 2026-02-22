#!/usr/bin/env bash
set -euo pipefail

UART_DEV="${UART_DEV:-/dev/ttyACM0}"
USBTMC_DEV="${USBTMC_DEV:-/dev/usbtmc0}"
DELAY_S="${DELAY_S:-1}"
TIMEOUT_S="${TIMEOUT_S:-30}"
MODE="${MODE:-DC}"
CSV_OUT="${CSV_OUT:-}"

usage() {
  cat <<'EOF'
Usage: measure_sleep_wake_current.sh [--uart /dev/ttyACM0] [--usb /dev/usbtmc0]
                                     [--delay-sec 1] [--timeout-sec 30]
                                     [--mode DC|AC] [--csv /tmp/sleep_wake_current.csv]

Behavior:
1. Flashes sleep_wake (C): ./flash_project.sh sleep_wake c
2. Waits for UART keyword "SLEEP", delays N seconds, measures current
3. Waits for UART keyword "AWAKE", delays N seconds, measures current
4. Prints both measurements in mA
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --uart) UART_DEV="$2"; shift 2 ;;
    --usb) USBTMC_DEV="$2"; shift 2 ;;
    --delay-sec) DELAY_S="$2"; shift 2 ;;
    --timeout-sec) TIMEOUT_S="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --csv) CSV_OUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ! -e "$UART_DEV" ]]; then
  echo "UART device not found: $UART_DEV" >&2
  exit 1
fi
if [[ ! -e "$USBTMC_DEV" ]]; then
  echo "USBTMC device not found: $USBTMC_DEV" >&2
  exit 1
fi

MODE_UPPER="$(printf '%s' "$MODE" | tr '[:lower:]' '[:upper:]')"
if [[ "$MODE_UPPER" != "DC" && "$MODE_UPPER" != "AC" ]]; then
  echo "Invalid --mode '$MODE' (use DC or AC)" >&2
  exit 2
fi

if lsof "$UART_DEV" >/dev/null 2>&1; then
  echo "UART device is busy: $UART_DEV" >&2
  lsof "$UART_DEV" >&2 || true
  exit 1
fi

measure_once() {
  local v=""
  printf "MEAS:CURR:%s?\n" "$MODE_UPPER" > "$USBTMC_DEV"
  sleep 0.05
  v="$(timeout 2 cat "$USBTMC_DEV" 2>/dev/null | tr -d '\r' | head -n1 || true)"
  if [[ -z "$v" ]]; then
    printf "MEAS:CURR:%s?\n" "$MODE_UPPER" > "$USBTMC_DEV"
    sleep 0.05
    v="$(timeout 2 cat "$USBTMC_DEV" 2>/dev/null | tr -d '\r' | head -n1 || true)"
  fi
  printf '%s' "$v"
}

amps_to_milliamps() {
  awk -v a="$1" 'BEGIN { printf "%.9f", a * 1000.0 }'
}

echo "Flashing sleep_wake (c)..."
./flash_project.sh sleep_wake c

echo "Waiting for SLEEP/AWAKE keywords on ${UART_DEV}..."
stty -F "$UART_DEV" 57600 -crtscts -ixon -ixoff raw -echo

sleep_a=""
wake_a=""
started_epoch="$(date +%s)"

while IFS= read -r line; do
  now_epoch="$(date +%s)"
  if (( now_epoch - started_epoch > TIMEOUT_S )); then
    echo "Timeout waiting for both keywords." >&2
    break
  fi

  if [[ -z "$sleep_a" && "$line" == *"SLEEP"* ]]; then
    sleep "$DELAY_S"
    sleep_a="$(measure_once)"
    echo "Captured SLEEP current."
    continue
  fi

  if [[ -n "$sleep_a" && -z "$wake_a" && "$line" == *"AWAKE"* ]]; then
    sleep "$DELAY_S"
    wake_a="$(measure_once)"
    echo "Captured WAKE current."
    break
  fi
done < <(timeout "$TIMEOUT_S" cat "$UART_DEV" | tr -d '\r')

if [[ -z "$sleep_a" || -z "$wake_a" ]]; then
  echo "Failed to capture both measurements. sleep='${sleep_a}' wake='${wake_a}'" >&2
  exit 1
fi

sleep_ma="$(amps_to_milliamps "$sleep_a")"
wake_ma="$(amps_to_milliamps "$wake_a")"

ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "SLEEP: ${sleep_ma} mA"
echo "AWAKE: ${wake_ma} mA"

if [[ -n "$CSV_OUT" ]]; then
  if [[ ! -e "$CSV_OUT" ]]; then
    echo "timestamp_utc,sleep_mA,wake_mA,sleep_A,wake_A" > "$CSV_OUT"
  fi
  echo "${ts},${sleep_ma},${wake_ma},${sleep_a},${wake_a}" >> "$CSV_OUT"
  echo "Wrote CSV row to ${CSV_OUT}"
fi
