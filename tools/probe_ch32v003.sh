#!/usr/bin/env bash
set -euo pipefail

OPENOCD_BIN="${OPENOCD_BIN:-openocd}"
OPENOCD_SCRIPTS="${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}"
ADAPTER_KHZ="${ADAPTER_KHZ:-4000}"
UART_DEV="${UART_DEV:-/dev/ttyACM1}"

usage() {
  cat <<'USAGE'
Usage: probe_ch32v003.sh [--openocd /path/to/openocd] [--scripts /path/to/openocd/scripts]
                         [--khz 4000] [--uart /dev/ttyACM1]

Checks:
1) WCH-Link USB presence
2) Optional UART device presence
3) CH32V003 debug probe via OpenOCD (if WCH scripts are available)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --openocd) OPENOCD_BIN="$2"; shift 2 ;;
    --scripts) OPENOCD_SCRIPTS="$2"; shift 2 ;;
    --khz) ADAPTER_KHZ="$2"; shift 2 ;;
    --uart) UART_DEV="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

echo "[probe] looking for WCH-Link USB device..."
if ! lsusb | grep -qiE '1a86:8010|WCH-Link'; then
  echo "[fail] WCH-Link not found on USB."
  exit 1
fi
echo "[ok] WCH-Link detected."

if [[ -e "$UART_DEV" ]]; then
  echo "[ok] UART device present: $UART_DEV"
else
  echo "[warn] UART device not found: $UART_DEV"
fi

if ! command -v "$OPENOCD_BIN" >/dev/null 2>&1; then
  echo "[fail] openocd not found: $OPENOCD_BIN"
  exit 1
fi

# Common script combinations across OpenOCD variants/forks.
combos=(
  "interface/wch-link.cfg target/ch32v003.cfg"
  "interface/wch-linke.cfg target/ch32v003.cfg"
  "interface/wch-link.cfg target/wch_riscv.cfg"
  "interface/wch-linke.cfg target/wch_riscv.cfg"
  "- target/wch-riscv.cfg"
)
found_candidate=0

run_probe_with() {
  local if_cfg="$1"
  local tgt_cfg="$2"

  if [[ "$if_cfg" == "-" ]]; then
    "$OPENOCD_BIN" -s "$OPENOCD_SCRIPTS" \
      -f "$tgt_cfg" \
      -c "adapter speed ${ADAPTER_KHZ}; init; reset halt; shutdown"
  else
    "$OPENOCD_BIN" -s "$OPENOCD_SCRIPTS" \
      -f "$if_cfg" -f "$tgt_cfg" \
      -c "adapter speed ${ADAPTER_KHZ}; init; reset halt; shutdown"
  fi
}

echo "[probe] searching for OpenOCD WCH/CH32 scripts in $OPENOCD_SCRIPTS ..."
for pair in "${combos[@]}"; do
  if_cfg="${pair%% *}"
  tgt_cfg="${pair##* }"
  if [[ "$if_cfg" == "-" && -f "$OPENOCD_SCRIPTS/$tgt_cfg" ]]; then
    found_candidate=1
    echo "[probe] trying: $tgt_cfg (self-contained target cfg)"
    if run_probe_with "$if_cfg" "$tgt_cfg"; then
      echo "[ok] CH32V003 probe attach succeeded via OpenOCD."
      exit 0
    fi
    echo "[warn] OpenOCD target cfg exists but probe attach failed: $tgt_cfg"
  elif [[ -f "$OPENOCD_SCRIPTS/$if_cfg" && -f "$OPENOCD_SCRIPTS/$tgt_cfg" ]]; then
    found_candidate=1
    echo "[probe] trying: $if_cfg + $tgt_cfg"
    if run_probe_with "$if_cfg" "$tgt_cfg"; then
      echo "[ok] CH32V003 probe attach succeeded via OpenOCD."
      exit 0
    fi
    echo "[warn] OpenOCD script pair exists but probe attach failed: $if_cfg + $tgt_cfg"
  fi
done

if [[ "$found_candidate" -eq 1 ]]; then
  echo "[fail] WCH script(s) were found, but probe attach did not succeed."
  echo "[info] Check USB permissions (udev), wiring, and that no other tool is holding the probe."
  exit 1
fi

echo "[fail] No usable WCH/CH32V003 OpenOCD script pair found in: $OPENOCD_SCRIPTS"
echo "[info] Your OpenOCD install likely lacks CH32V003 support scripts."
echo "[info] Options:"
echo "       1) build/install WCH-compatible OpenOCD (see tools/setup_wch_openocd.sh)"
echo "       2) use minichlink/wlink utility for CH32V003 bring-up"
exit 2
