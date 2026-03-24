# ESP32-S3 Target Notes

This is currently a documentation stub, not a full target scaffold.

Bench observations so far:

- built-in `USB JTAG/serial debug unit`
- USB VID:PID `303a:1001`
- serial console on `/dev/ttyACM0`
- `OpenOCD` works with:
  - `interface/esp_usb_jtag.cfg`
  - `target/esp32s3.cfg`

Current known device details from `esptool`:

- chip: `ESP32-S3`
- revision: `v0.2`
- flash: `16 MB`
- PSRAM: `8 MB embedded`
- crystal: `40 MHz`
- MAC: `3c:0f:02:d3:00:dc`

Practical implications:

- one USB cable is sufficient for serial console and JTAG
- flash backup and restore can be done over the native USB link

Current backup tooling:

- `tools/esp32s3_flash_backup.sh`
- `tools/esp32s3_flash_restore.sh`

Current known-good backup:

- `backups/esp32s3/esp32s3-flash-2026-03-24T00:05:49Z.bin`

Suggested next steps when this platform is resumed:

1. identify the exact board model
2. add a proper `target.toml`
3. add a small `blink` or serial test project
4. capture the serial boot log from the factory demo image before reflashing
