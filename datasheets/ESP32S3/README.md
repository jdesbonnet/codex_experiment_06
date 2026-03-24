# ESP32-S3 Documentation Index

This is currently a stub index for the new `ESP32-S3` platform.

Bench notes:

- USB descriptor: `Espressif USB JTAG/serial debug unit`
- USB VID:PID: `303a:1001`
- current serial device: `/dev/ttyACM0`
- JTAG works over the native USB connection

Observed device details:

- chip: `ESP32-S3`
- revision: `v0.2`
- flash: `16 MB`
- PSRAM: `8 MB embedded`
- crystal: `40 MHz`
- MAC: `3c:0f:02:d3:00:dc`

Current local artifacts:

- firmware backup:
  - `backups/esp32s3/esp32s3-flash-2026-03-24T00:05:49Z.bin`
- backup manifest:
  - `backups/esp32s3/esp32s3-flash-2026-03-24T00:05:49Z.manifest`

Suggested documents to add here later:

1. `ESP32-S3` datasheet
2. `ESP32-S3` technical reference manual
3. `ESP32-S3` hardware design guidelines
4. `ESP32-S3` silicon errata / ECO notes
5. board-specific schematic and user guide once the exact module/board is identified

Local tooling relevant to this platform:

- `tools/esp32s3_flash_backup.sh`
- `tools/esp32s3_flash_restore.sh`
- `OpenOCD` with `interface/esp_usb_jtag.cfg` and `target/esp32s3.cfg`
