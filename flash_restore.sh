#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <backup.bin> [manifest]" >&2
  exit 2
fi

BACKUP_FILE=$1
MANIFEST_FILE=${2:-}

OPENOCD_BIN=${OPENOCD_BIN:-openocd}
OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}
PROJECT_SCRIPTS=${PROJECT_SCRIPTS:-./openocd}
PROJECT_CFG=${PROJECT_CFG:-./openocd/base.cfg}

FLASH_START=${FLASH_START:-0x00000000}
FLASH_SIZE_BYTES=${FLASH_SIZE_BYTES:-32768}
RESET_AFTER=${RESET_AFTER:-run}

RESTORE_DIR=$(dirname "${BACKUP_FILE}")
TIMESTAMP_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_FILE="${RESTORE_DIR}/flash-restore-${TIMESTAMP_UTC}.log"

{
  echo "[${TIMESTAMP_UTC}] flash_restore.sh starting"
  echo "[${TIMESTAMP_UTC}] BACKUP_FILE=${BACKUP_FILE}"
  echo "[${TIMESTAMP_UTC}] MANIFEST_FILE=${MANIFEST_FILE:-<none>}"
  echo "[${TIMESTAMP_UTC}] OPENOCD_BIN=${OPENOCD_BIN}"
  echo "[${TIMESTAMP_UTC}] OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS}"
  echo "[${TIMESTAMP_UTC}] PROJECT_SCRIPTS=${PROJECT_SCRIPTS}"
  echo "[${TIMESTAMP_UTC}] PROJECT_CFG=${PROJECT_CFG}"
  echo "[${TIMESTAMP_UTC}] FLASH_START=${FLASH_START}"
  echo "[${TIMESTAMP_UTC}] FLASH_SIZE_BYTES=${FLASH_SIZE_BYTES}"
  echo "[${TIMESTAMP_UTC}] RESET_AFTER=${RESET_AFTER}"
} | tee -a "${LOG_FILE}"

if [ -n "${MANIFEST_FILE}" ] && [ -f "${MANIFEST_FILE}" ]; then
  EXPECTED_SHA=$(grep '^sha256=' "${MANIFEST_FILE}" | head -n 1 | cut -d= -f2- || true)
  if [ -n "${EXPECTED_SHA}" ]; then
    ACTUAL_SHA=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')
    if [ "${EXPECTED_SHA}" != "${ACTUAL_SHA}" ]; then
      echo "[${TIMESTAMP_UTC}] sha256 mismatch: expected ${EXPECTED_SHA}, got ${ACTUAL_SHA}" | tee -a "${LOG_FILE}" >&2
      exit 3
    fi
  fi
fi

OPENOCD_ARGS=(
  -s "${PROJECT_SCRIPTS}"
  -s "${OPENOCD_SCRIPTS}"
  -f "${PROJECT_CFG}"
  -c "init"
  -c "reset halt"
  -c "flash write_image erase ${BACKUP_FILE} ${FLASH_START}"
  -c "verify_image ${BACKUP_FILE} ${FLASH_START}"
  -c "reset ${RESET_AFTER}"
  -c "shutdown"
)

"${OPENOCD_BIN}" "${OPENOCD_ARGS[@]}" 2>&1 | tee -a "${LOG_FILE}"
