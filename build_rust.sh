#!/usr/bin/env bash
set -euo pipefail

projects=("sram_test" "uart_smoke" "blink")

if [ $# -lt 1 ]; then
  echo "usage: $0 <project> [debug|release]" >&2
  echo "projects: ${projects[*]}" >&2
  exit 2
fi

project=$1
profile=${2:-release}

case "${project}" in
  sram_test) pkg="sram_test_rust" ;;
  uart_smoke) pkg="uart_smoke_rust" ;;
  blink) pkg="blink_rust" ;;
  *) echo "Unknown project: ${project}" >&2; exit 2 ;;
 esac

case "${profile}" in
  debug|release) ;;
  *) echo "Unknown profile: ${profile}" >&2; exit 2 ;;
 esac

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo not found. Install rustup/cargo first." >&2
  exit 2
fi

if [ "${profile}" = "release" ]; then
  cargo build -p "${pkg}" --release
else
  cargo build -p "${pkg}"
fi
