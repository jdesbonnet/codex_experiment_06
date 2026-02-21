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
