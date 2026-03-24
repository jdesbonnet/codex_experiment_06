# ESP32-S3 Target Notes

This is currently a documentation stub, not a full target scaffold.

Current attached board is most likely from the `JC3248W535` 3.5-inch
touchscreen board family sold by SpotPear and multiple re-sellers. SpotPear's
own documentation inconsistently refers to the board as both `JC3248W535` and
`JC4832W535`; treat those as the same family unless proven otherwise.

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
- installed demo firmware is a vendor demo, not a standard upstream image
- the USB-C connector is very likely wired to native USB `D-`/`D+`
  (`GPIO19`/`GPIO20`)
- on `ESP32-S3`, `USB Serial/JTAG` and `USB Device` share one on-chip PHY, so
  a HID application on the native USB connector would replace the current
  `USB Serial/JTAG` behavior during runtime

Current backup tooling:

- `tools/esp32s3_flash_backup.sh`
- `tools/esp32s3_flash_restore.sh`

Current known-good backup:

- `backups/esp32s3/esp32s3-flash-2026-03-24T00:05:49Z.bin`

Board-family notes:

- display: `3.5"` `320x480` capacitive touch LCD
- local brochure confirms display controller `AXS15231B`
- local brochure indicates `5V` input and typical board draw of about `150 mA`
- factory demo includes:
  - clock
  - weather
  - album/photo frame
  - MJPEG playback
  - MP3 playback
  - settings
- vendor docs indicate:
  - default firmware source code is **not** provided
  - sample Arduino code and LVGL/touch examples **are** provided
  - vendor publishes a factory firmware image and burn tool
  - the board supports automatic download

USB/HID notes:

- The current attached firmware uses Espressif's fixed-function
  `USB Serial/JTAG` path.
- A Stream Deck style implementation would instead need firmware built on the
  `USB Device Stack` / `TinyUSB` path and enumerate as `HID`.
- That is feasible on `ESP32-S3`, but not simultaneously with the current
  native `USB Serial/JTAG` runtime on the same connector unless extra hardware
  is added.
- A realistic workflow is:
  1. flash/debug using the current USB Serial/JTAG path
  2. boot HID application firmware for host-side testing
  3. use Wi-Fi, BLE, or a secondary serial/debug path for runtime logs/config

Useful external references:

- SpotPear user guide:
  - <https://spotpear.com/wiki/ESP32-S3-3.5-inch-LCD-Captive-TouchScreen-Display-480x320-Tablet-MP3-Video-Weather-Clock.html>
- SpotPear product page:
  - <https://spotpear.com/shop/ESP32-S3-3.5-inch-LCD-Captive-TouchScreen-Display-480x320-Tablet-MP3-Video-Weather-Clock/JC3248W535.html>
- Local product brochure:
  - `datasheets/ESP32S3/JC832W535_motherboard.pdf`
- ESP-IDF `USB Serial/JTAG Controller Console` guide:
  - <https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-guides/usb-serial-jtag-console.html>
- ESP-IDF `USB Device Stack` guide:
  - <https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-reference/peripherals/usb_device.html>
- ESP-IDF built-in JTAG guide:
  - <https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-guides/jtag-debugging/configure-builtin-jtag.html>
- local board notes:
  - `datasheets/ESP32S3/README.md`

Suggested next steps when this platform is resumed:

1. identify the exact board model
2. add a proper `target.toml`
3. add a small `blink` or serial test project
4. capture the serial boot log from the factory demo image before reflashing
