# LPC1114 Multi-Project Workspace

This repository supports multiple small projects in both C and Rust, sharing common code.

## Layout

- `common/` shared drivers and utilities
  - `common/include` and `common/src` (C)
  - `common/rust` (Rust shared crate)
  - `common/protocols` (target-agnostic protocol helpers)
  - `common/test_patterns` (reusable test logic)
- `projects/` per-project `main.c` and Rust `main.rs`
- `targets/` target-specific packages
  - `targets/lpc1114` (active target metadata + scaffold)
  - `targets/lpc824` (NXP LPC824 target scaffold)
  - `targets/lpc8xx` (family-common LPC8xx CMSIS core support)
  - `targets/ch32v003` (target scaffold)
  - `targets/tm4c123gxl` (TI Tiva C LaunchPad target scaffold)
  - `targets/stm32f103c8` (STM32F103C8 target scaffold)
- `linker/` linker script

Project implementation directories use `hardware_language_variant` (variant optional). Examples:
- `lpc1114_c`
- `lpc1114_rust`
- `ch32v003_c`
- `ch32v003_rust`
- `ch32v003_rust_shim`
- `tm4c123gxl_c`
- `tm4c123gxl_rust`
- `stm32f103c8_c`

## Dependencies (C)

- `gcc-arm-none-eabi`
- `binutils-arm-none-eabi`
- `libnewlib-arm-none-eabi`
- `arm-none-eabi-gdb`
- `gdb-multiarch`
- `openocd`

On Raspberry Pi OS (Trixie/Debian):

```sh
sudo apt update
sudo apt install gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi gdb-multiarch openocd
```

You can verify with:

```sh
./check-toolchain.sh
```

## Dependencies (Rust)

Install Rust via rustup and the Cortex-M targets:

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
rustup target add thumbv6m-none-eabi
rustup target add thumbv7em-none-eabi
```

## CH32V003 (WCH-Link + OpenOCD)

The CH32V003 uses WCH's single-wire debug interface. The stock `openocd` package from Raspberry Pi OS typically does not include WCH-Link scripts/driver support, so CH32V003 attach fails even when the probe is detected on USB.

### CH32V003 host dependencies

```sh
sudo apt update
sudo apt install -y \
  build-essential git pkg-config \
  autoconf automake libtool texinfo \
  cmake ninja-build \
  libusb-1.0-0-dev libhidapi-dev libjim-dev
```

### Probe CH32V003 support from this repo

Use:

```sh
./tools/probe_ch32v003.sh
```

What it checks:

- WCH-Link USB presence (`1a86:8010`)
- optional UART presence (default `/dev/ttyACM1`)
- availability of CH32/WCH OpenOCD scripts
- attach attempt (`init; reset halt; shutdown`) when scripts are found

If probe attach fails with `LIBUSB_ERROR_ACCESS`, add a udev rule for WCH-Link:

```sh
sudo tee /etc/udev/rules.d/99-wch-link.rules >/dev/null <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", ATTR{idProduct}=="8010", MODE="0666", TAG+="uaccess"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

You can override paths:

```sh
./tools/probe_ch32v003.sh \
  --openocd ./tools/wch-openocd/bin/openocd \
  --scripts ./tools/wch-openocd/share/openocd/scripts \
  --khz 4000 \
  --uart /dev/ttyACM1
```

### Build a WCH-capable OpenOCD (open-source fork)

One open-source fork with WCH-Link support is `cjacker/wch-openocd`.

```sh
mkdir -p third_party
git clone --recursive https://github.com/cjacker/wch-openocd.git third_party/wch-openocd
./tools/setup_wch_openocd.sh
```

## CH32V003 via ch32fun (recommended app flow)

For CH32V003 applications, this repo now supports `ch32fun` as the primary C framework.

Install CH32 toolchain prerequisites:

```sh
sudo apt update
sudo apt install -y \
  gcc-riscv64-unknown-elf \
  binutils-riscv64-unknown-elf \
  libusb-1.0-0-dev \
  libudev-dev
```

Current convention:
- CH32 C project sources live in `projects/<name>/ch32v003_c`
- each CH32 project has its own `Makefile` including `third_party/ch32fun/ch32fun/ch32fun.mk`
- each CH32 project also includes a local `funconfig.h` (required by `ch32fun.h`)
- flashing uses `minichlink` through ch32fun (`cv_flash`) by default
- CH32 Rust uses a Rust static library (`projects/<name>/ch32v003_rust`) linked via a ch32fun shim project (`projects/<name>/ch32v003_rust_shim`)

Rust prerequisites for CH32:

```sh
source "$HOME/.cargo/env"
rustup toolchain install nightly --profile minimal
rustup +nightly component add rust-src
```

If `third_party/ch32fun` is missing:

```sh
git clone --depth 1 https://github.com/cnlohr/ch32fun.git third_party/ch32fun
```

Example (already scaffolded):
- `projects/blink/ch32v003_c`
- `projects/blink/ch32v003_rust`
- `projects/blink/ch32v003_rust_shim`

Then probe with the locally installed binary/scripts:

```sh
./tools/probe_ch32v003.sh \
  --openocd ./tools/wch-openocd/bin/openocd \
  --scripts ./tools/wch-openocd/share/openocd/scripts
```

Current repo status for CH32V003:

- target package exists at `targets/ch32v003`
- OpenOCD probing helper exists at `tools/probe_ch32v003.sh`
- local WCH OpenOCD setup helper exists at `tools/setup_wch_openocd.sh`
- flash wrapper can program a CH32V003 image via `tools/flash.sh --target ch32v003 ... --image <file>`

## Multimeter (SDM3065X)

The SDM3065X appears as a USBTMC device (usually `/dev/usbtmc0`). A udev rule is used to allow non-root access:

```
/etc/udev/rules.d/99-sdm3065x-usbtmc.rules
SUBSYSTEM=="usbmisc", KERNEL=="usbtmc*", ATTRS{idVendor}=="f4ec", ATTRS{idProduct}=="1208", MODE="0666", TAG+="uaccess"
```

Reload rules (or replug the device) after changes:

```sh
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Per-instrument documentation:
- `docs/instruments/siglent_sdm3065x.md`

## Instrument Notes

Per-instrument setup, Linux access notes, and local-documentation links:

- `docs/instruments/README.md`
- `docs/instruments/siglent_sdm3065x.md`
- `docs/instruments/rigol_dp832.md`
- `docs/instruments/keysight_dsox3014a.md`
- `docs/instruments/hamamatsu_c12880ma_uart.md`
- `docs/instruments/fnirsi_dps150.md`
- `docs/instruments/webcam_microscope.md`

The Keysight scope now has a helper script:

- `tools/keysight_scope.py`

For this DSO-X 3014A with old firmware, LAN control on port `5025` proved more
reliable than USBTMC for waveform downloads.

## Pico 2 Debugprobe Reset Line (nRESET)

By default, the 3-pin debug cable does not carry target reset. To control LPC1114 `nRESET` from OpenOCD, use a custom `debugprobe_on_pico2` firmware build and one extra wire.

### Build custom debugprobe firmware (Pico 2)

Required source-level setting:
- `debugprobe/include/board_pico_config.h` must contain:
```c
#define PROBE_PIN_RESET 1
```
- This maps target reset control to Pico GPIO1 (active-low/open-drain behavior in firmware).

Quick check:
```sh
grep -n "PROBE_PIN_RESET" debugprobe/include/board_pico_config.h
```

If the line is missing, add it and rebuild.

```sh
sudo apt update
sudo apt install -y cmake ninja-build

cd /tmp
git clone --depth 1 https://github.com/raspberrypi/debugprobe.git
cd debugprobe
git submodule update --init --recursive

cmake -S . -B build_pico2 -G Ninja \
  -DPICO_BOARD=pico2 \
  -DDEBUG_ON_PICO=ON \
  -DPICO_SDK_FETCH_FROM_GIT=ON

cmake --build build_pico2 -j4
```

Output image:
- `/tmp/debugprobe/build_pico2/debugprobe_on_pico2.uf2`

### Flash the Pico 2 board

1. Hold `BOOTSEL` on Pico 2 and plug USB (or press reset while holding `BOOTSEL`) to enter USB mass-storage mode.
2. Copy UF2 to `RPI-RP2`.
3. Pico reboots into debugprobe firmware automatically.

Example:

```sh
cp /tmp/debugprobe/build_pico2/debugprobe_on_pico2.uf2 /media/$USER/RPI-RP2/
sync
```

### Wire the reset line

- Existing SWD/UART wiring remains as-is.
- Add one extra wire:
  - Pico 2 `GPIO1` (physical pin 2) -> LPC1114 `RESET/PIO0_0` (`nRESET`)
- Keep common GND between probe and target.

### OpenOCD reset usage

For hardware reset via probe SRST, use:

```tcl
reset_config srst_only srst_nogate connect_deassert_srst
```

You can test SRST toggling directly:

```sh
openocd -s /usr/share/openocd/scripts -f interface/cmsis-dap.cfg \
  -c "transport select swd; reset_config srst_only srst_open_drain connect_deassert_srst; init; adapter assert srst; sleep 500; adapter deassert srst; shutdown"
```

## Pico 2 Debugprobe Dual-CDC UART Mirror

The custom Pico 2 debugprobe firmware in use exposes two UART CDC interfaces:
- `CDC-ACM UART Interface` (primary R/W)
- `CDC-ACM UART Mirror` (monitor RX mirror, host TX ignored)

This allows one terminal to monitor UART output while tooling uses a separate port.

Detect current device mapping:

```sh
./tools/find_debugprobe_uart_ports.sh
```

Example output:
- primary: `/dev/ttyACM0`
- mirror: `/dev/ttyACM2`

For scripting:

```sh
eval "$(./tools/find_debugprobe_uart_ports.sh --env)"
echo "$DEBUGPROBE_UART_PRIMARY"
echo "$DEBUGPROBE_UART_MIRROR"
```

## Build

C build:

```sh
make PROJECT=sram_test
```

Rust build (helper script):

```sh
./build_rust.sh sram_test release
```

Outputs:
- C: `build/<project>/<project>.elf`
- Rust: `target/thumbv6m-none-eabi/<profile>/<project>_rust`

Target-aware build wrapper:

```sh
./tools/build.sh --target lpc1114 --lang c --project blink
./tools/build.sh --target lpc1114 --lang rust --project blink --profile release
./tools/build.sh --target lpc824 --lang c --project blink
./tools/build.sh --target ch32v003 --lang c --project blink
./tools/build.sh --target ch32v003 --lang rust --project blink
./tools/build.sh --target tm4c123gxl --lang c --project blink
./tools/build.sh --target tm4c123gxl --lang rust --project tiny_vm
./tools/build.sh --target stm32f103c8 --lang c --project blink
```

## Flash

Interactive:

```sh
./flash_project.sh
```

When run without arguments it now prompts for target, then project.

Non-interactive:

```sh
./flash_project.sh sram_test c
./flash_project.sh sram_test rust
./flash_project.sh blink c tm4c123gxl
./flash_project.sh tiny_vm rust tm4c123gxl
./flash_project.sh blink c stm32f103c8
```

Rust default profile is `release` (override with `RUST_PROFILE=debug`).

Target-aware flash wrapper:

```sh
./tools/flash.sh --target lpc1114 --lang c --project sleep_wake
./tools/flash.sh --target lpc1114 --lang rust --project blink --profile release
./tools/flash.sh --target lpc824 --lang c --project blink
./tools/flash.sh --target ch32v003 --lang c --project blink
./tools/flash.sh --target ch32v003 --lang rust --project blink
./tools/flash.sh --target ch32v003 --lang c --project blink --image ./build/ch32v003/blink/blink.elf
./tools/flash.sh --target tm4c123gxl --lang c --project blink
./tools/flash.sh --target tm4c123gxl --lang rust --project tiny_vm
./tools/flash.sh --target stm32f103c8 --lang c --project blink
```

For `ch32v003`:
- default path is ch32fun `cv_flash` when `projects/<project>/ch32v003_c/Makefile` exists and `--image` is not provided
- Rust path uses ch32fun shim `cv_flash` when `projects/<project>/ch32v003_rust_shim/Makefile` exists and `--image` is not provided
- OpenOCD image flashing path is still available with `--image`
- if using OpenOCD mode and `--image` is omitted, wrapper checks:
- `build/ch32v003/<project>/<project>.elf`
- `build/ch32v003/<project>/<project>.bin`
- `build/ch32v003/<project>/<project>.hex`

For `tm4c123gxl`:
- current support is C and Rust
- wrapper builds `projects/<project>/tm4c123gxl_c` or `projects/<project>/tm4c123gxl_rust` when `--image` is omitted
- wrapper flashes through the on-board TI ICDI debugger using `targets/tm4c123gxl/openocd/base.cfg`
- set `TI_ICDI_SERIAL=<serial>` if multiple TI ICDI probes are connected
- TM4C Rust workspace artifacts are emitted under `target/thumbv7em-none-eabi/<profile>/`

For `stm32f103c8`:
- current support is C only
- wrapper builds `projects/<project>/stm32f103c8_c` when `--image` is omitted
- wrapper flashes through the Raspberry Pi `CMSIS-DAP` debugprobe using `targets/stm32f103c8/openocd/base.cfg`
- current `blink` implementation assumes a common `Blue Pill` style LED on `PC13` (active-low)

## Projects

- `sram_test`: SRAM tests + bandwidth
- `uart_smoke`: simple UART message
- `blink`: toggles PIO1_0
- `power_floor`: deep-sleep floor-current characterization image
- `tiny_vm`: tiny interpreted VM project (cross-target LPC1114 + CH32V003 + TM4C123GXL + STM32F103C8)

## tiny_vm

Runtime now exists on both targets and executes uploaded bytecode frames:
- `projects/tiny_vm/lpc1114_c`
- `projects/tiny_vm/lpc1114_rust`
- `projects/tiny_vm/ch32v003_c`
- `projects/tiny_vm/tm4c123gxl_c`
- `projects/tiny_vm/tm4c123gxl_rust`
- `projects/tiny_vm/stm32f103c8_c`

Upload frame format:
- magic: `TVM1`
- length: little-endian `uint16`
- payload: bytecode
- checksum: `sum(payload) & 0xff`

Runtime behavior:
- 15-second boot upload window after reset
- then continuous wait for the next valid upload frame

Host tools:
- assembler: `tools/vm_asm.py`
- minimal C-like frontend: `tools/vm_cc.py`
- uploader: `tools/vm_upload.py`
- SHA-1 case generator: `tools/gen_tiny_vm_sha1_case.py`
- host regression tests: `tools/test_vm_tools.py`
- hardware regression tests: `tools/test_tiny_vm_hardware.py`

Current VM includes:
- immediates: `PUSH8`, `PUSH16`, `PUSH32`
- arithmetic/comparison: `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, `EQ`, `LT`
- scratch memory: `MGET`, `MSET`, `MGET32`, `MSET32`
- bitwise/shift: `AND`, `OR`, `XOR`, `NOT`, `SHL`, `SHR`, `ROL`, `ROR`
- locals: `LGET`, `LSET`

Example flow:

```sh
./tools/vm_cc.py projects/tiny_vm/tests/count10.cvm.c -o /tmp/count10.bin
./tools/flash.sh --target lpc1114 --lang c --project tiny_vm
./tools/vm_upload.py /tmp/count10.bin --port /dev/ttyACM1 --baud 57600
```

TM4C123GXL manual sanity check:

```sh
./tools/vm_cc.py projects/tiny_vm/tests/count10.cvm.c -o /tmp/count10.bin
./tools/flash.sh --target tm4c123gxl --lang c --project tiny_vm
./tools/vm_upload.py /tmp/count10.bin --port /dev/ttyACM2 --baud 115200
```

STM32F103C8 manual sanity check:

```sh
./tools/vm_cc.py projects/tiny_vm/tests/count10.cvm.c -o /tmp/count10.bin
./tools/flash.sh --target stm32f103c8 --lang c --project tiny_vm
./tools/vm_upload.py /tmp/count10.bin --port /dev/ttyACM0 --baud 57600
```

Run the hardware regression suite:

```sh
python3 tools/test_tiny_vm_hardware.py
python3 tools/test_tiny_vm_hardware.py --runtime-lang rust
python3 tools/test_tiny_vm_hardware.py --runtime-lang rust --no-flash
```

Prime demo:
```sh
./tools/vm_cc.py projects/tiny_vm/tests/primes1000.cvm.c -o /tmp/primes1000.bin
./tools/vm_upload.py /tmp/primes1000.bin --port /dev/ttyACM1 --baud 57600
```

Collatz max-step demo:
```sh
./tools/vm_cc.py projects/tiny_vm/tests/collatz_max.cvm.c -o /tmp/collatz_max.bin
./tools/vm_upload.py /tmp/collatz_max.bin --port /dev/ttyACM1 --baud 57600
```

Web debugger visualization docs:
- `docs/web_debugger_visualization_proposal.md`
- `docs/web_debugger_api_contract.md`

`tiny_vm` C vs Rust analysis:
- `docs/tiny_vm_c_vs_rust_analysis.md`

FNIRSI DPI-150 USB protocol notes:
- `docs/fnirsi_dpi_150_usb_protocol.md`
