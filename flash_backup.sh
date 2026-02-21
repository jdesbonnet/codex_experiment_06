#!/usr/bin/env bash
set -euo pipefail

OPENOCD_BIN=${OPENOCD_BIN:-openocd}
OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}
PROJECT_SCRIPTS=${PROJECT_SCRIPTS:-./openocd}
PROJECT_CFG=${PROJECT_CFG:-./openocd/base.cfg}

FLASH_START=${FLASH_START:-0x00000000}
FLASH_SIZE_BYTES=${FLASH_SIZE_BYTES:-32768}

BACKUP_DIR=${BACKUP_DIR:-./backups}
TIMESTAMP_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BACKUP_FILE="${BACKUP_DIR}/flash-${TIMESTAMP_UTC}.bin"
MANIFEST_FILE="${BACKUP_DIR}/flash-${TIMESTAMP_UTC}.manifest"
LOG_FILE="${BACKUP_DIR}/flash-${TIMESTAMP_UTC}.log"

mkdir -p "${BACKUP_DIR}"

{
  echo "[${TIMESTAMP_UTC}] flash_backup.sh starting"
  echo "[${TIMESTAMP_UTC}] OPENOCD_BIN=${OPENOCD_BIN}"
  echo "[${TIMESTAMP_UTC}] OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS}"
  echo "[${TIMESTAMP_UTC}] PROJECT_SCRIPTS=${PROJECT_SCRIPTS}"
  echo "[${TIMESTAMP_UTC}] PROJECT_CFG=${PROJECT_CFG}"
  echo "[${TIMESTAMP_UTC}] FLASH_START=${FLASH_START}"
  echo "[${TIMESTAMP_UTC}] FLASH_SIZE_BYTES=${FLASH_SIZE_BYTES}"
  echo "[${TIMESTAMP_UTC}] BACKUP_FILE=${BACKUP_FILE}"
} | tee -a "${LOG_FILE}"

OPENOCD_ARGS=(
  -s "${PROJECT_SCRIPTS}"
  -s "${OPENOCD_SCRIPTS}"
  -f "${PROJECT_CFG}"
  -c "init"
  -c "reset halt"
  -c "dump_image ${BACKUP_FILE} ${FLASH_START} ${FLASH_SIZE_BYTES}"
  -c "shutdown"
)

"${OPENOCD_BIN}" "${OPENOCD_ARGS[@]}" 2>&1 | tee -a "${LOG_FILE}"

SHA256=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')
{
  echo "timestamp_utc=${TIMESTAMP_UTC}"
  echo "flash_start=${FLASH_START}"
  echo "flash_size_bytes=${FLASH_SIZE_BYTES}"
  echo "backup_file=${BACKUP_FILE}"
  echo "sha256=${SHA256}"
} | tee -a "${MANIFEST_FILE}"
