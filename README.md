# LPC1114 Multi-Project Workspace

This repository now supports multiple small projects sharing common code.

## Layout

- `common/` shared drivers and utilities
- `projects/` per-project `main.c`
- `linker/` linker script

## Dependencies

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

## Build

```sh
make PROJECT=sram_test
```

Outputs:
- `build/<project>/<project>.elf`
- `build/<project>/<project>.bin`

## Flash (OpenOCD)

Example:

```sh
openocd -s /usr/share/openocd/scripts -s ./openocd -f ./openocd/base.cfg \
  -c "init; reset halt; flash write_image erase build/sram_test/sram_test.elf; reset run; shutdown"
```

## Projects

- `sram_test`: SRAM tests + bandwidth
- `uart_smoke`: simple UART message
- `blink`: toggles PIO1_2
