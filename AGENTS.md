# Agent Instructions

## Purpose

Keep this file concise. Detailed notes belong in:

- `datasheets/CATALOG.md`
- `docs/instruments/README.md`
- `targets/<target>/README.md`

Check those local docs before searching the internet.

## Environment

- Host: Raspberry Pi 5, 64-bit Raspberry Pi OS (Debian Trixie)
- Timestamps: ISO-8601 UTC with `Z`
- Main debug probe: Pico 2 running custom `debugprobe_on_pico2`
- Probe docs:
  - `datasheets/raspberrypi-3pin-debug-spec.pdf`
  - <https://www.raspberrypi.com/documentation/microcontrollers/debug-probe.html>
- The probe is not official Raspberry Pi Debug Probe hardware
- `PROBE_PIN_RESET` is enabled on Pico 2 `GPIO1`

## Active Hardware Summaries

### LPC1114

Default attached MCU target: `LPC1114FN28/102`.

- SWD via the Pico 2 debugprobe
- No external crystal; use the internal oscillator
- Dedicated reset wire:
  - Pico 2 `GPIO1` -> LPC1114 `nRESET` (`RESET/PIO0_0`)
- LED:
  - `PIO1_2` -> LED -> resistor -> GND
- `23LC1024` SRAM wiring:
  - `PIO0_2` -> `CS`
  - `PIO0_6` -> `SCK`
  - `PIO0_8` -> `SO`
  - `PIO0_9` -> `SI`
- Docs: `datasheets/LPC1114/LPC111X.pdf`, `datasheets/LPC1114/UM10398.pdf`, `targets/lpc1114/README.md`

### STM32F103C8

- SWD via the Pico 2 debugprobe
- Current UART bring-up:
  - `USART1` on `PA9` / `PA10`
  - `57600` baud through the debugprobe UART
- SD card socket wiring:
  - `PA4` -> SD pin `1`
  - `PA5` -> SD pin `5`
  - `PA6` -> SD pin `7`
  - `PA7` -> SD pin `2`
  - `3.3V` and `GND` connected
- Docs: `targets/stm32f103c8/README.md`, `datasheets/SD_Cards/README.md`, `datasheets/STM32F103C8/README.md`

### Papilio One

- USB interface: `FT2232` (`0403:6010`)
- Working JTAG path uses `OpenOCD` with FTDI channel `0`
- Observed FPGA JTAG IDCODE: `0x41c22093`
- Inferred FPGA: `Xilinx XC3S500E`
- Docs: `targets/papilio_one/README.md`, `targets/papilio_one/openocd/base.cfg`, `datasheets/Papilio_One/README.md`

### ESP32-S3

- Native `USB JTAG/serial` path works over one cable
- Current serial device has enumerated as `/dev/ttyACM0`
- `OpenOCD` works with `interface/esp_usb_jtag.cfg` and `target/esp32s3.cfg`
- Current attached board is most likely `JC3248W535` / `JC3248W535C`
  3.5-inch touchscreen board family
- SpotPear vendor docs are the current best match
- Current backup tooling:
  - `tools/esp32s3_flash_backup.sh`
  - `tools/esp32s3_flash_restore.sh`
- Docs: `targets/esp32s3/README.md`, `datasheets/ESP32S3/README.md`

### LPC8xx Family

The repository may target `LPC810`, `LPC812`, and `LPC824`.
Prefer shared `lpc8xx` family code plus thin per-device overlays.
- Current local docs for `LPC824` are in:
  - `datasheets/LPC82x/README.md`
  - `targets/lpc824/README.md`

## Debugprobe UART Workflow

UART0 is connected to the debugprobe UART. The probe exposes:

- primary R/W interface (`CDC-ACM UART Interface`)
- mirrored RX monitor interface (`CDC-ACM UART Mirror`)

Detect current mapping with `./tools/find_debugprobe_uart_ports.sh`.
Preferred workflow: agent uses primary R/W, user uses mirror.
Use `57600`, `8N1`, no flow control.

## Repository Conventions

### Project naming

Under `projects/<project>/`, use `hardware_language_variant` (`variant`
optional), for example `lpc1114_c`, `lpc1114_rust`, `ch32v003_c`.
Apply the same principle to target support.

### Code standards

- Use ISO-8601 UTC timestamps with `Z`
- Document references in comments for algorithms and calculations
- Prefer generous logging unless it materially affects timing

### Tool scripts

- Scripts in `./tools` should provide `--verbose`
- Missing files and locked resources should produce single-line human-readable messages

### Web UI

- Prefer a lab-instrument dashboard style over generic web-app styling
- Support both light and dark themes where practical
- For scope-like displays:
  - light theme should read like a white engineering plot
  - dark theme should read like a scope display
  - use a single trace color family with faded persistence
  - put key controls below and beside the plot in an instrument-like layout
- Current ultrasonic viewer reference: `tools/ultrasonic_waveform_webapp/README.md`

### Git

- Backticks in commit messages have been problematic; avoid careless use

## Permissions Already Granted

- run `openocd` on target devices
- run scripts in `./tools`
- open UART on `/dev/ttyACM*`
- access USB test and measurement equipment
- write datasheets into `./datasheets`

## Instruments

Available instruments include the Siglent `SDM3065X-SC`, Rigol `DP832`,
Keysight `DSO-X 3014A`, Hamamatsu `C12880MA`, Fnirsi `DPS-150`, and a webcam
microscope.
If a needed instrument is missing, ask the user to connect it.
Per-instrument notes: `docs/instruments/README.md`

## Tools

- OpenOCD: <https://github.com/openocd-org/openocd>
