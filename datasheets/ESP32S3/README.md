# ESP32-S3 Documentation Index

This directory currently records bench notes and vendor links for the attached
`ESP32-S3` touchscreen board.

Most likely board family:

- `JC3248W535` / `JC3248W535C`
- SpotPear's own pages sometimes call the same board `JC4832W535`
- user-supplied product page was an AliExpress listing
- closest vendor documentation match is the SpotPear `JC3248W535` board family

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

Observed factory/demo firmware behavior:

- clock
- weather
- album/photo frame
- MJPEG video playback
- MP3 playback
- settings
- touch UI

SpotPear user-guide notes for the matching board family:

- factory weather/clock firmware uses Wi-Fi provisioning
- on first network setup it starts an AP named `My-Ap`
- default AP password is `12345678`
- web control is available by browsing to the IP shown in the Wi-Fi settings page

That matches the style of firmware installed on the attached device closely
enough to treat SpotPear's documentation as the current best match.

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

## Board-family resources

Primary reference page:

- SpotPear user guide:
  - <https://spotpear.com/wiki/ESP32-S3-3.5-inch-LCD-Captive-TouchScreen-Display-480x320-Tablet-MP3-Video-Weather-Clock.html>

Relevant statements from that guide:

- the default firmware source code is **not** provided
- Arduino examples are provided
- LVGL display and touch examples are provided
- the matching factory firmware image is published separately

Direct vendor resource links from the guide:

- demo/sample package:
  - <https://cdn.static.spotpear.com/uploads/picture/learn/ESP32/esp32-s3-touch-3.5/1-Demo.rar>
- schematic / I/O package:
  - <https://cdn.static.spotpear.com/uploads/picture/learn/ESP32/esp32-s3-touch-3.5/5-IO-pin-distribution.zip>
- driver IC datasheets:
  - <https://cdn.static.spotpear.com/uploads/picture/learn/ESP32/esp32-s3-touch-3.5/4-Driver_IC_Data_Sheet.zip>
- factory firmware image:
  - <https://cdn.static.spotpear.com/uploads/picture/learn/ESP32/esp32-s3-touch-3.5/JC3248W535C_I_Y_EN-80M.bin>

Inferences and caveats:

- The SpotPear board family appears to match the attached hardware closely, but
  this is still an inference from public product descriptions and the observed
  factory demo behavior.
- Community reports indicate the display controller is likely `AXS15231B` and
  the touch path is `I2C`, but this should be verified from the vendor
  schematic or driver package before being treated as canonical.
- Our own full-flash backup remains the primary restore path:
  - `backups/esp32s3/esp32s3-flash-2026-03-24T00:05:49Z.bin`
