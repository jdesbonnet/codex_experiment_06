# ESP32-S3 Documentation Index

This directory currently records bench notes and vendor links for the attached
`ESP32-S3` touchscreen board.

Most likely board family:

- `JC3248W535` / `JC3248W535C`
- SpotPear's own pages sometimes call the same board `JC4832W535`
- local brochure filename uses `JC832W535`, which may be a vendor naming
  variant or a typo; treat it as part of the same board family until proven
  otherwise
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

Brochure-confirmed hardware details from
`datasheets/ESP32S3/JC832W535_motherboard.pdf`:

- MCU: `ESP32-S3`
- display size: `3.5"` TFT IPS
- display resolution: `320x480`
- touch: capacitive
- display controller: `AXS15231B`
- operating voltage: `5V`
- typical power consumption: about `150 mA`
- module dimensions: `94.5 x 62.0 mm`
- display area: `73.4 x 49.0 mm`
- operating temperature: `-20 C` to `70 C`
- storage temperature: `-30 C` to `80 C`
- supports Wi-Fi and Bluetooth
- supports lithium battery power supply

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

## USB architecture implications

This matters for any HID / Stream Deck style firmware on this board.

What is known:

- the attached board currently enumerates as Espressif `USB JTAG/serial debug unit`
- Espressif documents `USB Serial/JTAG` on `ESP32-S3` as a fixed-function
  hardware device
- Espressif also documents that `USB Device` mode and `USB Serial/JTAG` share a
  single on-chip PHY
- SpotPear says this board supports automatic download, which is consistent
  with the USB-C connector being wired to the native USB pins

Practical conclusion:

- a USB HID keyboard / Stream Deck style application is plausible on this board
- but the firmware would need to use the `USB Device Stack` / `TinyUSB` path
  instead of `USB Serial/JTAG`
- you should not expect simultaneous use of:
  - native USB HID to the host
  - native USB Serial/JTAG debugging
  on the same connector without extra hardware

Realistic development workflow:

1. flash and debug with the current `USB Serial/JTAG` path
2. boot a `TinyUSB HID` application for host-side testing
3. use Wi-Fi, BLE, or a secondary serial path for runtime diagnostics/config

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

Local brochure:

- `datasheets/ESP32S3/JC832W535_motherboard.pdf`
  - product brochure for this board family
  - confirms `AXS15231B`, `320x480`, capacitive touch, `5V`, and typical
    `150 mA` consumption

Inferences and caveats:

- The SpotPear board family appears to match the attached hardware closely, but
  this is still an inference from public product descriptions and the observed
  factory demo behavior.
- Community reports indicate the display controller is likely `AXS15231B` and
  the touch path is `I2C`; the brochure now confirms `AXS15231B`, but the touch
  bus should still be verified from the vendor schematic or driver package
  before being treated as canonical.
- Our own full-flash backup remains the primary restore path:
  - `backups/esp32s3/esp32s3-flash-2026-03-24T00:05:49Z.bin`

Official USB references:

- `USB Serial/JTAG Controller Console`
  - <https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-guides/usb-serial-jtag-console.html>
- `USB Device Stack`
  - <https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-reference/peripherals/usb_device.html>
- `Configure ESP32-S3 Built-in JTAG Interface`
  - <https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-guides/jtag-debugging/configure-builtin-jtag.html>
