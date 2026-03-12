# SD FatFs

This project is the library-based comparison point for `sd_fat32_ro`.

It uses the existing STM32F103C8 SPI-mode SD block driver together with the
current official ChaN `FatFs R0.16` release configured for read-only operation.

Vendored source files live in `projects/sd_fatfs/stm32f103c8_c/fatfs/` and
include the upstream `LICENSE.txt`.

Current scope:

- SD card initialization in SPI mode
- `FatFs` mount of the first primary FAT partition
- root-directory listing
- read-only file reads from the boot partition

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
- current `sd_fatfs` (`FatFs R0.16`): `text=7836 data=8 bss=20`

The `FatFs` stack usage is not reflected in `bss`, so compare runtime stack
use separately from the linker-size numbers.

## Build

```sh
./tools/build.sh --target stm32f103c8 --lang c --project sd_fatfs
```

## Flash

```sh
./tools/flash.sh --target stm32f103c8 --lang c --project sd_fatfs
```
