#!/usr/bin/env bash
set -euo pipefail

TARGET=""
LANG=""
PROJECT=""
IMAGE=""
RUST_PROFILE="${RUST_PROFILE:-release}"
OPENOCD_BIN="${OPENOCD_BIN:-openocd}"
OPENOCD_SCRIPTS="${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}"
PROJECT_SCRIPTS="${PROJECT_SCRIPTS:-./openocd}"
ADAPTER_KHZ="${ADAPTER_KHZ:-4000}"
TI_ICDI_SERIAL="${TI_ICDI_SERIAL:-}"

have_riscv_toolchain() {
  command -v riscv64-elf-gcc >/dev/null 2>&1 \
    || command -v riscv64-unknown-elf-gcc >/dev/null 2>&1 \
    || command -v riscv-none-elf-gcc >/dev/null 2>&1
}

usage() {
  cat <<'EOF'
Usage: flash.sh --target <lpc1114|ch32v003|tm4c123gxl> --lang <c|rust> --project <name>
                [--profile <release|debug>] [--image <path/to/image.{elf|bin|hex}>]

Examples:
  ./tools/flash.sh --target lpc1114 --lang c --project sleep_wake
  ./tools/flash.sh --target lpc1114 --lang rust --project blink --profile release
  ./tools/flash.sh --target ch32v003 --lang c --project blink
  ./tools/flash.sh --target ch32v003 --lang rust --project blink
  ./tools/flash.sh --target ch32v003 --lang c --project blink --image ./build/ch32/blink.elf
  ./tools/flash.sh --target tm4c123gxl --lang c --project blink
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --lang) LANG="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --profile) RUST_PROFILE="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
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
    RUST_PROFILE="$RUST_PROFILE" ./flash_project.sh "$PROJECT" "$LANG"
    ;;
  ch32v003)
    CH32FUN_DIR="projects/${PROJECT}/ch32v003_c"
    CH32FUN_RUST_DIR="projects/${PROJECT}/ch32v003_rust_shim"
    if [[ ! -f "${CH32FUN_DIR}/Makefile" ]]; then
      CH32FUN_DIR="projects/${PROJECT}/ch32fun"
    fi
    if [[ ! -f "${CH32FUN_RUST_DIR}/Makefile" ]]; then
      CH32FUN_RUST_DIR="projects/${PROJECT}/ch32fun_rust"
    fi

    # Preferred path: ch32fun + minichlink for CH32V003 projects.
    if [[ -z "$IMAGE" && -f "${CH32FUN_DIR}/Makefile" && "$LANG" == "c" ]]; then
      if ! have_riscv_toolchain; then
        echo "Missing RISC-V GCC toolchain (expected one of: riscv64-elf-gcc, riscv64-unknown-elf-gcc, riscv-none-elf-gcc)." >&2
        echo "On Raspberry Pi OS/Debian: sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf" >&2
        exit 2
      fi
      make -C "${CH32FUN_DIR}" cv_flash
      exit 0
    fi

    if [[ -z "$IMAGE" && -f "${CH32FUN_RUST_DIR}/Makefile" && "$LANG" == "rust" ]]; then
      if ! have_riscv_toolchain; then
        echo "Missing RISC-V GCC toolchain (expected one of: riscv64-elf-gcc, riscv64-unknown-elf-gcc, riscv-none-elf-gcc)." >&2
        echo "On Raspberry Pi OS/Debian: sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf" >&2
        exit 2
      fi
      make -C "${CH32FUN_RUST_DIR}" cv_flash
      exit 0
    fi

    if [[ "$LANG" != "c" && "$LANG" != "rust" ]]; then
      echo "Invalid --lang '$LANG' (expected c or rust)." >&2
      exit 2
    fi

    # Prefer local WCH-capable OpenOCD by default.
    if [[ "$OPENOCD_BIN" == "openocd" && -x "./tools/wch-openocd/bin/openocd" ]]; then
      OPENOCD_BIN="./tools/wch-openocd/bin/openocd"
    fi
    if [[ "$OPENOCD_SCRIPTS" == "/usr/share/openocd/scripts" && -d "./tools/wch-openocd/share/openocd/scripts" ]]; then
      OPENOCD_SCRIPTS="./tools/wch-openocd/share/openocd/scripts"
    fi

    if [[ -z "$IMAGE" ]]; then
      for candidate in \
        "build/ch32v003/${PROJECT}/${PROJECT}.elf" \
        "build/ch32v003/${PROJECT}/${PROJECT}.bin" \
        "build/ch32v003/${PROJECT}/${PROJECT}.hex"
      do
        if [[ -f "$candidate" ]]; then
          IMAGE="$candidate"
          break
        fi
      done
    fi

    if [[ -z "$IMAGE" ]]; then
      echo "For ch32v003, pass --image <path/to/elf|bin|hex> (or place output under build/ch32v003/${PROJECT}/)." >&2
      exit 2
    fi
    if [[ ! -f "$IMAGE" ]]; then
      echo "Image not found: $IMAGE" >&2
      exit 2
    fi
    if [[ ! -x "$OPENOCD_BIN" && "$OPENOCD_BIN" != "openocd" ]]; then
      echo "OpenOCD binary not executable: $OPENOCD_BIN" >&2
      exit 2
    fi

    CFG="targets/ch32v003/openocd/base.cfg"
    if [[ ! -f "$CFG" ]]; then
      echo "Missing OpenOCD config: $CFG" >&2
      exit 2
    fi

    echo "Flashing CH32V003 image: $IMAGE"
    echo "OpenOCD: $OPENOCD_BIN"
    echo "Scripts: $OPENOCD_SCRIPTS"
    "$OPENOCD_BIN" \
      -s "$OPENOCD_SCRIPTS" \
      -f "$CFG" \
      -c "adapter speed ${ADAPTER_KHZ}; init; reset halt; program {$IMAGE} verify reset exit"
    ;;
  tm4c123gxl)
    if [[ "$LANG" == "c" ]]; then
      TM4C_DIR="projects/${PROJECT}/tm4c123gxl_c"
      if [[ ! -f "${TM4C_DIR}/Makefile" ]]; then
        echo "TM4C123GXL C project not found: ${TM4C_DIR}/Makefile" >&2
        exit 2
      fi

      if [[ -z "$IMAGE" ]]; then
        make -C "${TM4C_DIR}" all
        IMAGE="${TM4C_DIR}/${PROJECT}.elf"
      fi
    elif [[ "$LANG" == "rust" ]]; then
      if [[ -f "${HOME}/.cargo/env" ]]; then
        # shellcheck source=/dev/null
        source "${HOME}/.cargo/env"
      fi
      TM4C_RUST_MANIFEST="projects/${PROJECT}/tm4c123gxl_rust/Cargo.toml"
      TM4C_RUST_BIN="${PROJECT}_tm4c123gxl_rust"
      if [[ ! -f "${TM4C_RUST_MANIFEST}" ]]; then
        echo "TM4C123GXL Rust project not found: ${TM4C_RUST_MANIFEST}" >&2
        exit 2
      fi

      if [[ -z "$IMAGE" ]]; then
        if [[ "$RUST_PROFILE" == "release" ]]; then
          cargo build --manifest-path "${TM4C_RUST_MANIFEST}" --target thumbv7em-none-eabi --release
          IMAGE="target/thumbv7em-none-eabi/release/${TM4C_RUST_BIN}"
        else
          cargo build --manifest-path "${TM4C_RUST_MANIFEST}" --target thumbv7em-none-eabi
          IMAGE="target/thumbv7em-none-eabi/debug/${TM4C_RUST_BIN}"
        fi
      fi
    else
      echo "Invalid --lang '$LANG' (expected c or rust)" >&2
      exit 2
    fi

    if [[ ! -f "$IMAGE" ]]; then
      echo "Image not found: $IMAGE" >&2
      exit 2
    fi

    CFG="targets/tm4c123gxl/openocd/base.cfg"
    if [[ ! -f "$CFG" ]]; then
      echo "Missing OpenOCD config: $CFG" >&2
      exit 2
    fi

    OPENOCD_ARGS=(
      -s "$OPENOCD_SCRIPTS"
      -s "$PROJECT_SCRIPTS"
      -f "$CFG"
    )

    if [[ -n "$TI_ICDI_SERIAL" ]]; then
      OPENOCD_ARGS+=(-c "set TI_ICDI_SERIAL ${TI_ICDI_SERIAL}")
    fi

    OPENOCD_ARGS+=(
      -c "init"
      -c "reset halt"
      -c "flash write_image erase {$IMAGE}"
      -c "verify_image {$IMAGE}"
      -c "reset run"
      -c "shutdown"
    )

    echo "Flashing TM4C123GXL image: $IMAGE"
    echo "OpenOCD: $OPENOCD_BIN"
    echo "Scripts: $OPENOCD_SCRIPTS"
    echo "Project scripts: $PROJECT_SCRIPTS"
    if [[ -n "$TI_ICDI_SERIAL" ]]; then
      echo "ICDI serial: $TI_ICDI_SERIAL"
    fi
    "$OPENOCD_BIN" "${OPENOCD_ARGS[@]}"
    ;;
  *)
    echo "Unknown target: $TARGET" >&2
    exit 2
    ;;
esac
