#!/usr/bin/env bash
set -euo pipefail

OPENOCD_BIN=${OPENOCD_BIN:-openocd}
OPENOCD_SCRIPTS=${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}
PROJECT_SCRIPTS=${PROJECT_SCRIPTS:-./openocd}
PROJECT_CFG=${PROJECT_CFG:-./openocd/base.cfg}
RUST_TARGET=${RUST_TARGET:-thumbv6m-none-eabi}
RUST_PROFILE=${RUST_PROFILE:-release}

projects=("sram_test" "uart_smoke" "blink")

usage() {
  echo "usage: $0 [project] [lang]" >&2
  echo "  project: ${projects[*]}" >&2
  echo "  lang: c|rust (default: c)" >&2
  echo "  env: RUST_PROFILE=release|debug" >&2
}

project=""
lang="c"

if [ $# -ge 1 ]; then
  project=$1
fi
if [ $# -ge 2 ]; then
  lang=$2
fi

if [ -z "${project}" ]; then
  select project in "${projects[@]}"; do
    if [ -n "${project}" ]; then
      echo "Selected project: ${project}"
      break
    fi
    echo "Invalid selection."
  done
else
  found=0
  for p in "${projects[@]}"; do
    if [ "${project}" = "${p}" ]; then
      found=1
      break
    fi
  done
  if [ ${found} -ne 1 ]; then
    echo "Unknown project: ${project}" >&2
    usage
    exit 2
  fi
fi

if [ "${lang}" != "c" ] && [ "${lang}" != "rust" ]; then
  echo "Unknown language: ${lang}" >&2
  usage
  exit 2
fi

echo "Selected project: ${project} (${lang})"

echo "Building ${project} (${lang})..."
if [ "${lang}" = "c" ]; then
  make PROJECT="${project}"
  elf="build/${project}/${project}.elf"
else
  if [ -f "${HOME}/.cargo/env" ]; then
    # Ensure rustup/cargo environment is loaded for non-interactive shells.
    # shellcheck source=/dev/null
    source "${HOME}/.cargo/env"
  fi
  if ! command -v cargo >/dev/null 2>&1; then
    echo "cargo not found. Install rustup/cargo first." >&2
    exit 2
  fi
  if [ "${RUST_PROFILE}" = "release" ]; then
    cargo build -p "${project}_rust" --release
    elf="target/${RUST_TARGET}/release/${project}_rust"
  else
    cargo build -p "${project}_rust"
    elf="target/${RUST_TARGET}/debug/${project}_rust"
  fi
fi

echo "Flashing ${project} (${lang})..."
"${OPENOCD_BIN}" -s "${OPENOCD_SCRIPTS}" -s "${PROJECT_SCRIPTS}" -f "${PROJECT_CFG}" \
  -c "init; reset halt; flash write_image erase ${elf}; reset run; shutdown"
