#!/usr/bin/env bash
# Inventory of toolchains and helpers used by this repo.
#
# Each section is independent: an MCU-only contributor does not need the
# Theia / Playwright bits, and someone using just the host-side simulator
# does not need an ARM toolchain. Missing items in optional sections do
# not fail the script.
#
# Install commands for all of these are in README.md "Dependencies" sections.

set -uo pipefail

missing_required=0

required() {
    local name=$1
    if command -v "$name" >/dev/null 2>&1; then
        printf "  ok   %-26s %s\n" "$name" "($(command -v "$name"))"
        local v
        v=$("$name" --version 2>/dev/null | head -n 1) || true
        [ -n "${v:-}" ] && printf "       %s\n" "$v"
    else
        printf "  MISS %-26s required\n" "$name"
        missing_required=1
    fi
}

optional() {
    local name=$1
    local what=$2
    if command -v "$name" >/dev/null 2>&1; then
        printf "  ok   %-26s %s\n" "$name" "($(command -v "$name"))"
    else
        printf "  --   %-26s optional (%s)\n" "$name" "$what"
    fi
}

section() {
    echo
    echo "== $* =="
}

section "ARM Cortex-M toolchain (lpc1114 / lpc8xx / stm32f103c8 / tm4c123gxl)"
required arm-none-eabi-gcc
required arm-none-eabi-objcopy
required arm-none-eabi-size
required gdb-multiarch
required openocd
optional arm-none-eabi-gdb "alternative to gdb-multiarch"

section "Rust (embedded ports)"
optional rustc  "needed for *_rust projects"
optional cargo  "needed for *_rust projects"
if command -v rustup >/dev/null 2>&1; then
    rustup target list --installed 2>/dev/null \
      | grep -E "thumbv6m-none-eabi|thumbv7em-none-eabi" \
      | sed 's/^/       installed target: /'
fi

section "CH32V003 / RISC-V (ch32fun)"
optional riscv64-unknown-elf-gcc "needed for ch32v003_c builds"
optional minichlink              "default flash path (via ch32fun cv_flash)"
if [ -d third_party/ch32fun ]; then
    echo "  ok   third_party/ch32fun"
else
    echo "  --   third_party/ch32fun        optional (clone https://github.com/cnlohr/ch32fun.git)"
fi
if [ -d tools/wch-openocd ]; then
    echo "  ok   tools/wch-openocd"
else
    echo "  --   tools/wch-openocd          optional (run tools/setup_wch_openocd.sh)"
fi

section "Host dev environment (tools/dev_env)"
optional node       "Theia IDE"
optional npm        "Theia IDE"
optional npx        "Theia IDE / Playwright"
optional python3    "simulator + DAP server"
optional ffmpeg     "Playwright video recording"
optional google-chrome "Playwright e2e (alt: chromium)"

echo
if [ $missing_required -ne 0 ]; then
    echo "one or more REQUIRED tools (ARM toolchain) are missing - see README.md 'Dependencies (C)'"
    exit 1
fi
echo "required tools: all present"
exit 0
