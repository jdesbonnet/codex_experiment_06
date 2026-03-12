# SD Raw Write Bench

This project measures raw SD-card write throughput on the `STM32F103C8` by
writing directly into a host-preallocated contiguous file region.

Current reserved region:

- file: `CODXLOG.BIN`
- `start_lba = 13053`
- `sector_count = 16384`

Current scope:

- initialize the SD card in SPI mode
- write directly to the reserved LBA range
- benchmark both:
  - single-block writes
  - multi-block writes
- verify the first and last written sectors by readback

Important notes:

- this bypasses `FatFs` in the write loop
- it modifies the contents of `CODXLOG.BIN`
- if the host recreates or moves the file, the hardcoded LBA range becomes invalid

## Build

```sh
make -C projects/sd_raw_write_bench/stm32f103c8_c clean all \
  STM32_BENCH_SYSCLK_HZ=64000000 \
  SD_SPI_BENCH_DIV=8 \
  SD_WRITE_BENCH_BYTES=262144
```

## Sweep

```sh
./tools/benchmark_sd_raw_write_speeds.py --sysclk-hz 64000000 --bytes 262144
```
