#!/usr/bin/env bash
set -euo pipefail

TARGET=""
LANG=""
PROJECT=""
RUST_PROFILE="${RUST_PROFILE:-release}"

have_riscv_toolchain() {
  command -v riscv64-elf-gcc >/dev/null 2>&1 \
    || command -v riscv64-unknown-elf-gcc >/dev/null 2>&1 \
    || command -v riscv-none-elf-gcc >/dev/null 2>&1
}

usage() {
  cat <<'EOF'
Usage: build.sh --target <lpc1114|ch32v003|tm4c123gxl> --lang <c|rust> --project <name> [--profile <release|debug>]

Examples:
  ./tools/build.sh --target lpc1114 --lang c --project blink
  ./tools/build.sh --target lpc1114 --lang rust --project blink --profile debug
  ./tools/build.sh --target ch32v003 --lang c --project blink
  ./tools/build.sh --target ch32v003 --lang rust --project blink
  ./tools/build.sh --target tm4c123gxl --lang c --project blink
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --lang) LANG="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --profile) RUST_PROFILE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$TARGET" || -z "$LANG" || -z "$PROJECT" ]]; then
  usage
  exit 2
fi

if [[ "$LANG" != "c" && "$LANG" != "rust" ]]; then
  echo "Invalid --lang '$LANG' (expected c or rust)" >&2
  exit 2
fi

case "$TARGET" in
  lpc1114)
    if [[ "$LANG" == "c" ]]; then
      make PROJECT="$PROJECT"
    else
      if [[ -f "${HOME}/.cargo/env" ]]; then
        # shellcheck source=/dev/null
        source "${HOME}/.cargo/env"
      fi
      RUST_DIR="projects/${PROJECT}/lpc1114_rust"
      if [[ ! -f "${RUST_DIR}/Cargo.toml" ]]; then
        RUST_DIR="projects/${PROJECT}/rust"
      fi
      if [[ ! -f "${RUST_DIR}/Cargo.toml" ]]; then
        echo "Rust project not found: projects/${PROJECT}/lpc1114_rust/Cargo.toml (or legacy projects/${PROJECT}/rust/Cargo.toml)" >&2
        exit 2
      fi
      if [[ "$RUST_PROFILE" == "release" ]]; then
        cargo build -p "${PROJECT}_rust" --release
      else
        cargo build -p "${PROJECT}_rust"
      fi
    fi
    ;;
  ch32v003)
    if [[ "$LANG" == "c" ]]; then
      CH32FUN_DIR="projects/${PROJECT}/ch32v003_c"
      if [[ ! -f "${CH32FUN_DIR}/Makefile" ]]; then
        CH32FUN_DIR="projects/${PROJECT}/ch32fun"
      fi
      if [[ ! -f "${CH32FUN_DIR}/Makefile" ]]; then
        echo "CH32 C project not found: projects/${PROJECT}/ch32v003_c/Makefile (or legacy projects/${PROJECT}/ch32fun/Makefile)" >&2
        exit 2
      fi
      if ! have_riscv_toolchain; then
        echo "Missing RISC-V GCC toolchain (expected one of: riscv64-elf-gcc, riscv64-unknown-elf-gcc, riscv-none-elf-gcc)." >&2
        echo "On Raspberry Pi OS/Debian: sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf" >&2
        exit 2
      fi
      make -C "${CH32FUN_DIR}" build
    elif [[ "$LANG" == "rust" ]]; then
      CH32FUN_RUST_DIR="projects/${PROJECT}/ch32v003_rust_shim"
      if [[ ! -f "${CH32FUN_RUST_DIR}/Makefile" ]]; then
        CH32FUN_RUST_DIR="projects/${PROJECT}/ch32fun_rust"
      fi
      if [[ ! -f "${CH32FUN_RUST_DIR}/Makefile" ]]; then
        echo "CH32 Rust shim project not found: projects/${PROJECT}/ch32v003_rust_shim/Makefile (or legacy projects/${PROJECT}/ch32fun_rust/Makefile)" >&2
        exit 2
      fi
      if ! have_riscv_toolchain; then
        echo "Missing RISC-V GCC toolchain (expected one of: riscv64-elf-gcc, riscv64-unknown-elf-gcc, riscv-none-elf-gcc)." >&2
        echo "On Raspberry Pi OS/Debian: sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf" >&2
        exit 2
      fi
      make -C "${CH32FUN_RUST_DIR}" build
    else
      echo "Invalid --lang '$LANG' (expected c or rust)" >&2
      exit 2
    fi
    ;;
  tm4c123gxl)
    if [[ "$LANG" != "c" ]]; then
      echo "TM4C123GXL currently supports C projects only." >&2
      exit 2
    fi

    TM4C_DIR="projects/${PROJECT}/tm4c123gxl_c"
    if [[ ! -f "${TM4C_DIR}/Makefile" ]]; then
      echo "TM4C123GXL C project not found: ${TM4C_DIR}/Makefile" >&2
      exit 2
    fi

    make -C "${TM4C_DIR}" all
    ;;
  *)
    echo "Unknown target: $TARGET" >&2
    exit 2
    ;;
esac
