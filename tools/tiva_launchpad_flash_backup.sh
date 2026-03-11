#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: tools/tiva_launchpad_flash_backup.sh [options]

Dump the TM4C123GH6PM application flash from the TI Tiva C LaunchPad.

Options:
  --backup-dir <dir>      Directory for backup artifacts.
  --output <file>         Explicit output image path.
  --adapter-serial <id>   TI ICDI USB serial number to bind OpenOCD to.
  --flash-start <addr>    Flash base address. Default: 0x00000000
  --flash-size <bytes>    Bytes to back up. Default: 262144
  --verbose               Print the OpenOCD command line before running it.
  -h, --help              Show this help text.
EOF
}

OPENOCD_BIN=${OPENOCD_BIN:-openocd}
OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}
PROJECT_SCRIPTS=${PROJECT_SCRIPTS:-./openocd}
PROJECT_CFG=${PROJECT_CFG:-./openocd/tiva_tm4c123gxl.cfg}

FLASH_START=${FLASH_START:-0x00000000}
FLASH_SIZE_BYTES=${FLASH_SIZE_BYTES:-262144}
BACKUP_DIR=${BACKUP_DIR:-./backups/tiva_tm4c123gxl}
BACKUP_FILE=${BACKUP_FILE:-}
TI_ICDI_SERIAL=${TI_ICDI_SERIAL:-}
VERBOSE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --backup-dir)
      shift
      BACKUP_DIR=${1:-}
      ;;
    --output)
      shift
      BACKUP_FILE=${1:-}
      ;;
    --adapter-serial)
      shift
      TI_ICDI_SERIAL=${1:-}
      ;;
    --flash-start)
      shift
      FLASH_START=${1:-}
      ;;
    --flash-size)
      shift
      FLASH_SIZE_BYTES=${1:-}
      ;;
    --verbose)
      VERBOSE=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [ -z "${BACKUP_DIR}" ]; then
  echo "Backup directory must not be empty." >&2
  exit 2
fi

if [ ! -f "${PROJECT_CFG}" ]; then
  echo "OpenOCD config not found: ${PROJECT_CFG}" >&2
  exit 2
fi

mkdir -p "${BACKUP_DIR}"

TIMESTAMP_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
if [ -z "${BACKUP_FILE}" ]; then
  BACKUP_FILE="${BACKUP_DIR}/tm4c123gh6pm-flash-${TIMESTAMP_UTC}.bin"
fi

MANIFEST_FILE="${BACKUP_FILE%.bin}.manifest"
LOG_FILE="${BACKUP_FILE%.bin}.log"

OPENOCD_ARGS=()
if [ -n "${TI_ICDI_SERIAL}" ]; then
  OPENOCD_ARGS+=(-c "set TI_ICDI_SERIAL ${TI_ICDI_SERIAL}")
fi
OPENOCD_ARGS+=(
  -s "${PROJECT_SCRIPTS}"
  -s "${OPENOCD_SCRIPTS}"
  -f "${PROJECT_CFG}"
  -c "init"
  -c "halt"
  -c "dump_image ${BACKUP_FILE} ${FLASH_START} ${FLASH_SIZE_BYTES}"
  -c "shutdown"
)

{
  echo "[${TIMESTAMP_UTC}] tiva_launchpad_flash_backup.sh starting"
  echo "[${TIMESTAMP_UTC}] OPENOCD_BIN=${OPENOCD_BIN}"
  echo "[${TIMESTAMP_UTC}] OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS}"
  echo "[${TIMESTAMP_UTC}] PROJECT_SCRIPTS=${PROJECT_SCRIPTS}"
  echo "[${TIMESTAMP_UTC}] PROJECT_CFG=${PROJECT_CFG}"
  echo "[${TIMESTAMP_UTC}] TI_ICDI_SERIAL=${TI_ICDI_SERIAL:-<auto>}"
  echo "[${TIMESTAMP_UTC}] FLASH_START=${FLASH_START}"
  echo "[${TIMESTAMP_UTC}] FLASH_SIZE_BYTES=${FLASH_SIZE_BYTES}"
  echo "[${TIMESTAMP_UTC}] BACKUP_FILE=${BACKUP_FILE}"
} | tee "${LOG_FILE}"

if [ "${VERBOSE}" -eq 1 ]; then
  printf '[%s] OpenOCD command:' "${TIMESTAMP_UTC}" | tee -a "${LOG_FILE}"
  printf ' %q' "${OPENOCD_BIN}" "${OPENOCD_ARGS[@]}" | tee -a "${LOG_FILE}"
  printf '\n' | tee -a "${LOG_FILE}"
fi

if ! "${OPENOCD_BIN}" "${OPENOCD_ARGS[@]}" 2>&1 | tee -a "${LOG_FILE}"; then
  echo "OpenOCD failed while backing up the LaunchPad flash. Check ${LOG_FILE}." >&2
  exit 1
fi

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Backup file was not created: ${BACKUP_FILE}" >&2
  exit 1
fi

ACTUAL_SIZE=$(stat -c%s "${BACKUP_FILE}")
EXPECTED_SIZE=$((FLASH_SIZE_BYTES))
if [ "${ACTUAL_SIZE}" -ne "${EXPECTED_SIZE}" ]; then
  echo "Backup size mismatch: expected ${EXPECTED_SIZE} bytes, got ${ACTUAL_SIZE} bytes." >&2
  exit 1
fi

SHA256=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')
{
  echo "timestamp_utc=${TIMESTAMP_UTC}"
  echo "target=tm4c123gh6pm"
  echo "flash_start=${FLASH_START}"
  echo "flash_size_bytes=${FLASH_SIZE_BYTES}"
  echo "backup_file=${BACKUP_FILE}"
  echo "sha256=${SHA256}"
} | tee "${MANIFEST_FILE}"

echo "Backup complete:"
echo "  image: ${BACKUP_FILE}"
echo "  manifest: ${MANIFEST_FILE}"
echo "  sha256: ${SHA256}"
