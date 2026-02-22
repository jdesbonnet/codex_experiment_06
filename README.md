# LPC1114 Multi-Project Workspace

This repository supports multiple small projects in both C and Rust, sharing common code.

## Layout

- `common/` shared drivers and utilities
  - `common/include` and `common/src` (C)
  - `common/rust` (Rust shared crate)
- `projects/` per-project `main.c` and Rust `main.rs`
- `linker/` linker script

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

Install Rust via rustup and the Cortex-M0 target:

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
rustup target add thumbv6m-none-eabi
```

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

## Pico 2 Debugprobe Reset Line (nRESET)

By default, the 3-pin debug cable does not carry target reset. To control LPC1114 `nRESET` from OpenOCD, use a custom `debugprobe_on_pico2` firmware build and one extra wire.

### Build custom debugprobe firmware (Pico 2)

This build path enables `PROBE_PIN_RESET` in the Pico board config (`GPIO1`).

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
- Rust: `projects/<project>/rust/target/thumbv6m-none-eabi/<profile>/<project>_rust`

## Flash

Interactive:

```sh
./flash_project.sh
```

Non-interactive:

```sh
./flash_project.sh sram_test c
./flash_project.sh sram_test rust
```

Rust default profile is `release` (override with `RUST_PROFILE=debug`).

## Projects

- `sram_test`: SRAM tests + bandwidth
- `uart_smoke`: simple UART message
- `blink`: toggles PIO1_0
- `power_floor`: deep-sleep floor-current characterization image
