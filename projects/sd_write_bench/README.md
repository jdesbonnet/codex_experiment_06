# SD Write Bench

This project measures file-level SD-card write throughput on the
`STM32F103C8` using the existing SPI-mode SD block driver and `FatFs R0.16`.

Current scope:

- mount the FAT32 boot partition
- create or overwrite `CODXBEN.BIN`
- write `64 KiB` in `4096`-byte chunks
- report write-loop time, sync/close time, and total throughput over UART

Important notes:

- this is a file-level benchmark, not a raw-sector maximum-throughput test
- it modifies the card by creating or overwriting `CODXBEN.BIN`
- current default SPI run prescaler is `/8`

Current implementation:

- `stm32f103c8_c`

## Build

```sh
./tools/build.sh --target stm32f103c8 --lang c --project sd_write_bench
```

## Flash

```sh
./tools/flash.sh --target stm32f103c8 --lang c --project sd_write_bench
```

## Sweep SPI Clock

```sh
./tools/benchmark_sd_spi_speeds.py --dividers 2,4,8,16,32,64
```

Longer, higher-clock run:

```sh
./tools/benchmark_sd_spi_speeds.py --sysclk-hz 64000000 --bytes 262144 --timeout 60
```

To build a single variant manually:

```sh
make -C projects/sd_write_bench/stm32f103c8_c clean all SD_SPI_BENCH_DIV=4
```

To override both MCU clock and file size manually:

```sh
make -C projects/sd_write_bench/stm32f103c8_c clean all \
  STM32_BENCH_SYSCLK_HZ=64000000 \
  SD_SPI_BENCH_DIV=4 \
  SD_WRITE_BENCH_BYTES=262144
```
