# SD FAT32 Read-Only

This project builds on the low-level `sd_spi_probe` work and adds a minimal
read-only `FAT32` layer for the STM32F103C8 target.

Current scope:

- SD card initialization in SPI mode
- MBR partition parsing
- FAT32 boot-sector parsing
- FAT32 `FSInfo` and first `FAT` sector reads
- root-directory listing
- read-only file access for short-name files in the root directory

Current implementation:

- `stm32f103c8_c`

## STM32F103C8 Wiring

- `PA4` -> SD card `pin 1` (`CS`)
- `PA5` -> SD card `pin 5` (`CLK`)
- `PA6` -> SD card `pin 7` (`MISO`)
- `PA7` -> SD card `pin 2` (`MOSI`)
- `PA9`/`PA10` -> debugprobe UART at `57600 8N1`

## Notes

This is a small handwritten `FAT32` reader intended to explore code size and
mechanics on embedded targets. It is intentionally narrower than `FatFs`.

The natural follow-up is a separate `sd_fatfs` project so we can compare:

- code size
- complexity
- feature coverage

## Build

```sh
./tools/build.sh --target stm32f103c8 --lang c --project sd_fat32_ro
```

## Flash

```sh
./tools/flash.sh --target stm32f103c8 --lang c --project sd_fat32_ro
```
