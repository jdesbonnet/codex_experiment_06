# SD FatFs

This project is the library-based comparison point for `sd_fat32_ro`.

It uses the existing STM32F103C8 SPI-mode SD block driver together with the
current official ChaN `FatFs R0.16` release configured for controlled read/write
testing.

Vendored source files live in `projects/sd_fatfs/stm32f103c8_c/fatfs/` and
include the upstream `LICENSE.txt`.

Current scope:

- SD card initialization in SPI mode
- `FatFs` mount of the first primary FAT partition
- root-directory listing
- file reads from the boot partition
- controlled single-file write test on the boot partition

Current implementation:

- `stm32f103c8_c`

## Notes

This is a comparison build, not yet the final long-term choice. It is useful
for measuring:

- code size
- complexity
- behavior versus the handwritten `sd_fat32_ro` path

Current measured sizes on STM32F103C8:

- handwritten `sd_fat32_ro`: `text=8672 data=4 bss=520`
- current `sd_fatfs` (`FatFs R0.16`): build-dependent, re-measure after changes

The `FatFs` stack usage is not reflected in `bss`, so compare runtime stack
use separately from the linker-size numbers.

Current write test behavior:

- creates or overwrites `0:/CODXWR.TXT`
- writes `codex sd write test\r\n`
- calls `f_sync`
- reopens the file and verifies the prefix over UART

## Build

```sh
./tools/build.sh --target stm32f103c8 --lang c --project sd_fatfs
```

## Flash

```sh
./tools/flash.sh --target stm32f103c8 --lang c --project sd_fatfs
```

## Hardware Regression

```sh
./tools/test_sd_hardware.py --tests sd_fatfs --verbose
```

This test modifies the card by creating or overwriting `CODXWR.TXT` on the
FAT32 boot partition.
