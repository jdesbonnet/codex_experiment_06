#!/usr/bin/env bash
set -euo pipefail

OPENOCD_BIN=${OPENOCD_BIN:-openocd}
OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}
PROJECT_SCRIPTS=${PROJECT_SCRIPTS:-./openocd}
PROJECT_CFG=${PROJECT_CFG:-./openocd/base.cfg}

LOG_DIR=${LOG_DIR:-./debug_logs}
TIMESTAMP_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_FILE="${LOG_DIR}/openocd-${TIMESTAMP_UTC}.log"

mkdir -p "${LOG_DIR}"

{
  echo "[${TIMESTAMP_UTC}] openocd_debug.sh starting"
  echo "[${TIMESTAMP_UTC}] OPENOCD_BIN=${OPENOCD_BIN}"
  echo "[${TIMESTAMP_UTC}] OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS}"
  echo "[${TIMESTAMP_UTC}] PROJECT_SCRIPTS=${PROJECT_SCRIPTS}"
  echo "[${TIMESTAMP_UTC}] PROJECT_CFG=${PROJECT_CFG}"
  echo "[${TIMESTAMP_UTC}] LOG_FILE=${LOG_FILE}"
} | tee -a "${LOG_FILE}"

"${OPENOCD_BIN}" \
  -s "${PROJECT_SCRIPTS}" \
  -s "${OPENOCD_SCRIPTS}" \
  -f "${PROJECT_CFG}" \
  -c "init" \
  -c "reset halt" \
  2>&1 | tee -a "${LOG_FILE}"
