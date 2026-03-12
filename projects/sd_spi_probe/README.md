# SD SPI Probe

This project family is for low-level SD card bring-up before any filesystem
layer is added.

Current scope:

- card initialization in SPI mode
- metadata reads (`OCR`, `CID`, `CSD`)
- single-block reads
- MBR / partition table parsing
- volume boot sector parsing for `FAT12/16`, `FAT32`, and `exFAT`
- `FAT32` auxiliary metadata reads (`FSInfo`, first `FAT` sector)

Current implementation:

- `stm32f103c8_c`

## STM32F103C8 Wiring

- `PA4` -> SD card `pin 1` (`CS`)
- `PA5` -> SD card `pin 5` (`CLK`)
- `PA6` -> SD card `pin 7` (`MISO`)
- `PA7` -> SD card `pin 2` (`MOSI`)
- `PA9`/`PA10` -> debugprobe UART at `57600 8N1`

## Build

```sh
./tools/build.sh --target stm32f103c8 --lang c --project sd_spi_probe
```

## Flash

```sh
./tools/flash.sh --target stm32f103c8 --lang c --project sd_spi_probe
```
