#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: tools/esp32s3_flash_backup.sh [options]

Dump the full ESP32-S3 external flash over the built-in USB JTAG/serial link.

Options:
  --backup-dir <dir>      Directory for backup artifacts.
  --output <file>         Explicit output image path.
  --port <device>         Serial port. Default: /dev/ttyACM0
  --chip <name>           esptool chip name. Default: esp32s3
  --flash-size <bytes>    Bytes to back up. Default: 16777216
  --flash-offset <addr>   Flash offset. Default: 0x0
  --baud <baud>           Serial baud rate. Default: 2000000
  --before <mode>         esptool reset mode before access. Default: default-reset
  --after <mode>          esptool reset mode after access. Default: hard-reset
  --verbose               Print the esptool command line before running it.
  -h, --help              Show this help text.

Environment:
  ESPTOOL_BIN             Explicit esptool executable to use.

Notes:
  - Upstream esptool is recommended for ESP32-S3 backup.
  - Some distro-packaged esptool builds do not include the required stub files.
EOF
}

resolve_esptool_bin() {
  if [ -n "${ESPTOOL_BIN:-}" ]; then
    printf '%s\n' "${ESPTOOL_BIN}"
    return 0
  fi
  if [ -x "./.venv/bin/esptool" ]; then
    printf '%s\n' "./.venv/bin/esptool"
    return 0
  fi
  if [ -x "/tmp/esptool-venv/bin/esptool" ]; then
    printf '%s\n' "/tmp/esptool-venv/bin/esptool"
    return 0
  fi
  if command -v esptool >/dev/null 2>&1; then
    command -v esptool
    return 0
  fi
  if command -v esptool.py >/dev/null 2>&1; then
    command -v esptool.py
    return 0
  fi
  return 1
}

extract_flash_id_field() {
  local label=$1
  local file=$2
  sed -n "s/^${label}: //p" "${file}" | tail -n 1
}

PORT=${PORT:-/dev/ttyACM0}
CHIP=${CHIP:-esp32s3}
FLASH_SIZE_BYTES=${FLASH_SIZE_BYTES:-16777216}
FLASH_OFFSET=${FLASH_OFFSET:-0x0}
BACKUP_DIR=${BACKUP_DIR:-./backups/esp32s3}
BACKUP_FILE=${BACKUP_FILE:-}
BAUD=${BAUD:-2000000}
BEFORE_MODE=${BEFORE_MODE:-default-reset}
AFTER_MODE=${AFTER_MODE:-hard-reset}
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
    --port)
      shift
      PORT=${1:-}
      ;;
    --chip)
      shift
      CHIP=${1:-}
      ;;
    --flash-size)
      shift
      FLASH_SIZE_BYTES=${1:-}
      ;;
    --flash-offset)
      shift
      FLASH_OFFSET=${1:-}
      ;;
    --baud)
      shift
      BAUD=${1:-}
      ;;
    --before)
      shift
      BEFORE_MODE=${1:-}
      ;;
    --after)
      shift
      AFTER_MODE=${1:-}
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

if [ -z "${PORT}" ]; then
  echo "Serial port must not be empty." >&2
  exit 2
fi

if ! ESPTOOL=$(resolve_esptool_bin); then
  echo "No esptool executable found. Set ESPTOOL_BIN or install upstream esptool." >&2
  exit 2
fi

mkdir -p "${BACKUP_DIR}"

TIMESTAMP_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
if [ -z "${BACKUP_FILE}" ]; then
  BACKUP_FILE="${BACKUP_DIR}/esp32s3-flash-${TIMESTAMP_UTC}.bin"
fi

MANIFEST_FILE="${BACKUP_FILE%.bin}.manifest"
LOG_FILE="${BACKUP_FILE%.bin}.log"
FLASH_ID_FILE="${BACKUP_FILE%.bin}.flash-id.txt"

COMMON_ARGS=(
  --chip "${CHIP}"
  --port "${PORT}"
  --baud "${BAUD}"
  --before "${BEFORE_MODE}"
  --after "${AFTER_MODE}"
)

{
  echo "[${TIMESTAMP_UTC}] esp32s3_flash_backup.sh starting"
  echo "[${TIMESTAMP_UTC}] ESPTOOL=${ESPTOOL}"
  echo "[${TIMESTAMP_UTC}] PORT=${PORT}"
  echo "[${TIMESTAMP_UTC}] CHIP=${CHIP}"
  echo "[${TIMESTAMP_UTC}] FLASH_OFFSET=${FLASH_OFFSET}"
  echo "[${TIMESTAMP_UTC}] FLASH_SIZE_BYTES=${FLASH_SIZE_BYTES}"
  echo "[${TIMESTAMP_UTC}] BAUD=${BAUD}"
  echo "[${TIMESTAMP_UTC}] BEFORE_MODE=${BEFORE_MODE}"
  echo "[${TIMESTAMP_UTC}] AFTER_MODE=${AFTER_MODE}"
  echo "[${TIMESTAMP_UTC}] BACKUP_FILE=${BACKUP_FILE}"
} | tee "${LOG_FILE}"

if [ "${VERBOSE}" -eq 1 ]; then
  printf '[%s] esptool flash-id command:' "${TIMESTAMP_UTC}" | tee -a "${LOG_FILE}"
  printf ' %q' "${ESPTOOL}" "${COMMON_ARGS[@]}" flash-id | tee -a "${LOG_FILE}"
  printf '\n' | tee -a "${LOG_FILE}"
fi

if ! "${ESPTOOL}" "${COMMON_ARGS[@]}" flash-id 2>&1 | tee "${FLASH_ID_FILE}" | tee -a "${LOG_FILE}" >/dev/null; then
  echo "esptool flash-id failed. Check ${LOG_FILE}." >&2
  exit 1
fi

if [ "${VERBOSE}" -eq 1 ]; then
  printf '[%s] esptool read-flash command:' "${TIMESTAMP_UTC}" | tee -a "${LOG_FILE}"
  printf ' %q' "${ESPTOOL}" "${COMMON_ARGS[@]}" read-flash "${FLASH_OFFSET}" "${FLASH_SIZE_BYTES}" "${BACKUP_FILE}" | tee -a "${LOG_FILE}"
  printf '\n' | tee -a "${LOG_FILE}"
fi

if ! "${ESPTOOL}" "${COMMON_ARGS[@]}" read-flash "${FLASH_OFFSET}" "${FLASH_SIZE_BYTES}" "${BACKUP_FILE}" 2>&1 | tee -a "${LOG_FILE}"; then
  echo "esptool failed while backing up the ESP32-S3 flash. Check ${LOG_FILE}." >&2
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
CHIP_NAME=$(sed -n 's/^Detecting chip type\.\.\. //p' "${FLASH_ID_FILE}" | tail -n 1)
FEATURES=$(extract_flash_id_field "Features" "${FLASH_ID_FILE}" || true)
CRYSTAL=$(extract_flash_id_field "Crystal is" "${FLASH_ID_FILE}" || true)
MAC=$(extract_flash_id_field "MAC" "${FLASH_ID_FILE}" || true)
FLASH_SIZE_HUMAN=$(sed -n 's/^Detected flash size: //p' "${FLASH_ID_FILE}" | tail -n 1)

{
  echo "timestamp_utc=${TIMESTAMP_UTC}"
  echo "target=esp32s3"
  echo "chip=${CHIP_NAME:-${CHIP}}"
  echo "port=${PORT}"
  echo "flash_offset=${FLASH_OFFSET}"
  echo "flash_size_bytes=${FLASH_SIZE_BYTES}"
  echo "flash_size_human=${FLASH_SIZE_HUMAN:-unknown}"
  echo "baud=${BAUD}"
  echo "before_mode=${BEFORE_MODE}"
  echo "after_mode=${AFTER_MODE}"
  echo "features=${FEATURES:-unknown}"
  echo "crystal=${CRYSTAL:-unknown}"
  echo "mac=${MAC:-unknown}"
  echo "image=${BACKUP_FILE}"
  echo "log=${LOG_FILE}"
  echo "flash_id_log=${FLASH_ID_FILE}"
  echo "sha256=${SHA256}"
  echo "size_bytes=${ACTUAL_SIZE}"
} | tee "${MANIFEST_FILE}"

echo "Backup complete:"
echo "  image: ${BACKUP_FILE}"
echo "  manifest: ${MANIFEST_FILE}"
echo "  log: ${LOG_FILE}"
echo "  sha256: ${SHA256}"
