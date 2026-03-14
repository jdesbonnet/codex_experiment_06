# Agent Instructions


## Hardware setup:

You are running on a Raspberry Pi 5 running 64bit Raspberry Pi OS based on Debian Trixie.

Connected to the Raspberry Pi 5 via USB is a Raspberry Pi Pico 2 board running Raspberry Pi debugprobe firmware. The firmware currently in use is a custom `debugprobe_on_pico2` build with reset-line support enabled (`PROBE_PIN_RESET` on Pico 2 `GPIO1`). You will find documentation on the 3-pin interface in the datasheets directory file `raspberrypi-3pin-debug-spec.pdf` and general information at https://www.raspberrypi.com/documentation/microcontrollers/debug-probe.html. Keep in mind this is not the official Raspberry Pi Debug Probe hardware, but debugprobe firmware running on a Pico 2 board.

Before searching the internet for board or component documentation, check `datasheets/CATALOG.md` for locally cached PDFs and manuals.
For bench instrument setup, Linux access notes, and per-instrument entry points, also check `docs/instruments/README.md`.

This debugger probe is connected to the target device: an LPC1114FN28/102 ARM Cortex-M0 chip (part of the LPC111X family) via the ARM Serial Wire Debug (SWD) port. The pinout of this chip is documented in fig 13 of `datasheets/LPC1114/LPC111X.pdf`. You will find information about programming it in `datasheets/LPC1114/UM10398.pdf`. There is no external crystal for timing, so you will be using the internal oscillator.

In addition to SWD and UART, there is now a dedicated reset wire from Pico 2 `GPIO1` (physical pin 2) to LPC1114 `nRESET` (`RESET/PIO0_0`). This allows OpenOCD to control target SRST for reliable hardware reset pulses.

There is a Microchip 23LC1024 SRAM chip connected to it via pins: 
PIO0_2 (connected to 'CS' pin on 23LC1024 via white wire), 
PIO0_6 (connected to 'SCK' pin on 23LC1024 via green wire), 
PIO0_8 (connected to 'SO' pin on 23LC1024 via yellow wire), 
PIO0_9 (connected to 'SI' pin on 23LC1024 via blue wire).

There is a LED connected to PIO1_2. The other end of the LED is connected via a resistor to ground.

Otherwise there are no other peripherals.

There is also an `STM32F103C8` target board used in this repository. When working on that board:
- SWD is connected to the Raspberry Pi debugprobe
- current UART bring-up uses `USART1` on `PA9`/`PA10` through the debugprobe UART at `57600` baud
- an SD card socket is wired as follows:
  - `PA4` to SD socket pin `1`
  - `PA5` to SD socket pin `5`
  - `PA6` to SD socket pin `7`
  - `PA7` to SD socket pin `2`
  - `3.3V` and `GND` also connected to the SD socket
- for SD card protocol notes and external reference links, check `datasheets/SD_Cards/README.md`

There are also multiple NXP `LPC8xx` family devices in scope for this repository, including `LPC810`, `LPC812`, and `LPC824`. When adding support for this family, prefer a shared `lpc8xx` layer for common startup/CMSIS/BSP/OpenOCD code, with per-device overlays only for items that actually vary such as linker scripts, flash/RAM sizes, package pin maps, and board wiring.

## UART setup

UART0 is connected to the Raspberry Pi debugger probe UART.

The probe firmware now exposes two CDC UART interfaces:
- primary R/W interface (`CDC-ACM UART Interface`)
- mirrored RX monitor interface (`CDC-ACM UART Mirror`)

Device node numbering can change (`/dev/ttyACM*`). Detect current mapping with:
`./tools/find_debugprobe_uart_ports.sh`

Preferred workflow:
- agent uses primary R/W port
- user terminal monitor uses mirror port

Use 57600 baud, 8N1, no flow control.

## Software tools

You will find software to talk to the debugging probe here: https://github.com/openocd-org/openocd

## Project naming convention

For per-project implementation directories under `projects/<project>/`, use:
- `hardware_language_variant` (variant optional)
- examples: `lpc1114_c`, `lpc1114_rust`, `ch32v003_c`, `ch32v003_rust`, `ch32v003_rust_shim`

For target support, the same principle applies: if several MCUs share a vendor family, prefer a family-common target layer plus thin per-device overlays rather than copy/pasted full target directories.


## My code standards:

- For timestamps use ISO-6801 in UTC using the 'Z' suffix. For internal calculations Java ms epoch time is preferred. If resources are constrained and whole second resolution is acceptable then unix epoch time in seconds is acceptable.
- If performing calculations or implementing an algorithm it is important that references are documented in comments.
- During the development phase we will add plenty of logging (except where that logging might affect timing).


## Permission to perform actions without seeking confirmation

- Agent has permission to run openocd on target device.
- Agest has permission to run scripts in ./tools directory.
- Agent has permission to open UART on /dev/ttyACM0 (or any /dev/ttyACMx device).
- Agent has permission to access test and measurement equipment on USB bus.
- Agent has permission to write datasheets into the ./datasheets directory structure.


## Git operations

There is a repeating issue with commiting messages with backtick symbols. Keep this in mind before issuing git commit commands.

## Tool scripts

This project has many tooling scripts. Some common rules: always have a --verbose switch that will output debugging information. When expecting a file as an argument and the file does not exist a single line human friendly message should be displayed instead of a stack trace. If a resource (eg UART) is locked by another process: also a human friendly message is preferred.


## Test and measurement instruments

You have access to these instruments:

- Siglent SDM3065X-SC digital multimeter via USB
- Rigol DPS832 lab power supply (with mA resolution software upgrade) via USB
- Agilent/Keysight DSO-X 3014A digital oscilloscope and signal generator via USB
- Hamamatsu C12880MA spectrometer (GroupGets) plugged into Arduino which outputs a spectrum via UART
- Fnirsi DPS-150 lab power supply via USB
- Webcam microscope

Not all the instruments are plugged in all the time, so if you don't detect it 
ask me to plug it in.

Per-instrument notes:

- `docs/instruments/README.md`
