#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/third_party/wch-openocd"
INSTALL_DIR="${ROOT_DIR}/tools/wch-openocd"

JOBS="${JOBS:-$(nproc)}"
FORCE_RECONFIGURE=0

usage() {
  cat <<'EOF'
Usage: setup_wch_openocd.sh [--jobs N] [--force-reconfigure]

Builds and installs a WCH-Link-capable OpenOCD locally:
  source:  third_party/wch-openocd
  install: tools/wch-openocd

The script applies small compatibility patches needed on Debian/RPi OS.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --jobs) JOBS="$2"; shift 2 ;;
    --force-reconfigure) FORCE_RECONFIGURE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "[fail] Missing source tree: ${SRC_DIR}"
  echo "[info] Run:"
  echo "       git clone --recursive https://github.com/cjacker/wch-openocd.git ${SRC_DIR}"
  exit 1
fi

patch_file_once() {
  local file="$1"
  local needle="$2"
  local patch_cmd="$3"
  if grep -Fq "$needle" "$file"; then
    return 0
  fi
  eval "$patch_cmd"
}

echo "[setup] applying compatibility patches if needed..."

# Fix missing FILE definition in helper headers.
patch_file_once \
  "${SRC_DIR}/src/helper/log.h" \
  "#include <stdio.h>" \
  "sed -i '/#include <helper\\/command.h>/a #include <stdio.h>' '${SRC_DIR}/src/helper/log.h'"

patch_file_once \
  "${SRC_DIR}/src/helper/configuration.h" \
  "#include <stdio.h>" \
  "sed -i '/#include <helper\\/command.h>/a #include <stdio.h>' '${SRC_DIR}/src/helper/configuration.h'"

patch_file_once \
  "${SRC_DIR}/src/helper/jim-nvp.c" \
  "#include <stdio.h>" \
  "sed -i '/#include <string.h>/a #include <stdio.h>' '${SRC_DIR}/src/helper/jim-nvp.c'"

# Make warning path compatible with system libjim (no currentScriptObj usage).
if grep -Fq "interp->currentScriptObj" "${SRC_DIR}/src/openocd.c"; then
  perl -0pi -e "s@LOG_WARNING\\(\"DEPRECATED! use 'expr \\{ %s \\}' not 'expr %s' in \\\"%s\\\", line %d\",\\s*s, s, \\(\\(struct jim_scriptobj \\*\\)interp->currentScriptObj\\)->filename_obj->bytes,\\s*\\(\\(struct jim_scriptobj \\*\\)interp->currentScriptObj\\)->linenr\\);@LOG_WARNING(\"DEPRECATED! use 'expr { %s }' not 'expr %s'\", s, s);@s" "${SRC_DIR}/src/openocd.c"
fi

if [[ "${FORCE_RECONFIGURE}" -eq 1 || ! -f "${SRC_DIR}/Makefile" ]]; then
  echo "[setup] configuring..."
else
  echo "[setup] reconfiguring..."
fi

(
  cd "${SRC_DIR}"
  ./configure \
    --prefix="${INSTALL_DIR}" \
    --disable-werror \
    --enable-wlinke \
    --disable-ch347 \
    --disable-internal-libjaylink \
    --disable-jlink \
    --disable-internal-jimtcl
)

echo "[setup] building (jobs=${JOBS})..."
make -C "${SRC_DIR}" -j"${JOBS}"

echo "[setup] installing to ${INSTALL_DIR} ..."
make -C "${SRC_DIR}" install

echo "[setup] done."
echo "[setup] verify with:"
echo "        ./tools/probe_ch32v003.sh --openocd ./tools/wch-openocd/bin/openocd --scripts ./tools/wch-openocd/share/openocd/scripts"
