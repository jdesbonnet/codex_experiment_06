#!/usr/bin/env bash
set -euo pipefail

OPENOCD_BIN=${OPENOCD_BIN:-openocd}
ADAPTER_SPEED_KHZ=${ADAPTER_SPEED_KHZ:-1000}
PROJECT_CFG=${PROJECT_CFG:-./openocd/probe.cfg}
INTERFACE_CFG=${INTERFACE_CFG:-interface/cmsis-dap.cfg}
TARGET_CFG=${TARGET_CFG:-target/lpc11xx.cfg}
PROBE_COMMANDS=${PROBE_COMMANDS:-"init; reset halt; mdw 0x00000000 4; reg; shutdown"}

# Allow the user to point OpenOCD at its scripts directory if needed.
OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS:-}
if [ -z "${OPENOCD_SCRIPTS}" ] && [ -d "/usr/share/openocd/scripts" ]; then
  OPENOCD_SCRIPTS="/usr/share/openocd/scripts"
fi

PROJECT_SCRIPTS=${PROJECT_SCRIPTS:-}
if [ -z "${PROJECT_SCRIPTS}" ] && [ -d "./openocd" ]; then
  PROJECT_SCRIPTS="./openocd"
fi

TIMESTAMP_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_DIR=${LOG_DIR:-./probe_logs}
LOG_PATH="${LOG_DIR}/probe-${TIMESTAMP_UTC}.log"

mkdir -p "${LOG_DIR}"

OPENOCD_ARGS=()

if [ -n "${PROJECT_SCRIPTS}" ]; then
  OPENOCD_ARGS+=("-s" "${PROJECT_SCRIPTS}")
fi

if [ -n "${OPENOCD_SCRIPTS}" ]; then
  OPENOCD_ARGS+=("-s" "${OPENOCD_SCRIPTS}")
fi

if [ -f "${PROJECT_CFG}" ]; then
  OPENOCD_ARGS+=("-f" "${PROJECT_CFG}")
else
  OPENOCD_ARGS+=("-f" "${INTERFACE_CFG}" "-f" "${TARGET_CFG}" "-c" "adapter speed ${ADAPTER_SPEED_KHZ}" "-c" "transport select swd" "-c" "${PROBE_COMMANDS}")
fi

{
  echo "[${TIMESTAMP_UTC}] probe.sh starting"
  echo "[${TIMESTAMP_UTC}] OPENOCD_BIN=${OPENOCD_BIN}"
  echo "[${TIMESTAMP_UTC}] OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS:-<default>}"
  echo "[${TIMESTAMP_UTC}] PROJECT_SCRIPTS=${PROJECT_SCRIPTS:-<default>}"
  echo "[${TIMESTAMP_UTC}] PROJECT_CFG=${PROJECT_CFG}"
  echo "[${TIMESTAMP_UTC}] INTERFACE_CFG=${INTERFACE_CFG}"
  echo "[${TIMESTAMP_UTC}] TARGET_CFG=${TARGET_CFG}"
  echo "[${TIMESTAMP_UTC}] ADAPTER_SPEED_KHZ=${ADAPTER_SPEED_KHZ}"
  echo "[${TIMESTAMP_UTC}] PROBE_COMMANDS=${PROBE_COMMANDS}"
  echo "[${TIMESTAMP_UTC}] LOG_PATH=${LOG_PATH}"
} | tee -a "${LOG_PATH}"

"${OPENOCD_BIN}" "${OPENOCD_ARGS[@]}" 2>&1 | tee -a "${LOG_PATH}"
