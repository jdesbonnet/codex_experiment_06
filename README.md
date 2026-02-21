# LPC1114 Minimal Project

This is a minimal bare-metal project skeleton for the LPC1114FN28/102 (Cortex-M0).

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
make
```

Outputs:
- `build/lpc1114_min.elf`
- `build/lpc1114_min.bin`

## Flash (OpenOCD)

Example (adjust paths if needed):

```sh
openocd -s /usr/share/openocd/scripts -s ./openocd -f ./openocd/base.cfg \
  -c "init; reset halt; flash write_image erase build/lpc1114_min.elf; reset run; shutdown"
```

## Notes

- Linker script is `linker/lpc1114.ld` with 32 KB flash / 4 KB SRAM.
- Startup code is in `src/startup.c` (vector table + data/bss init).
- No peripheral init yet; `main()` is a placeholder loop.
