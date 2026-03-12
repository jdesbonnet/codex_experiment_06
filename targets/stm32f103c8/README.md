# STM32F103C8 Target

This target scaffold is for an `STM32F103C8` class Cortex-M3 device.

Implementation choices:

- CMSIS device support comes from the official ST `cmsis-device-f1` package
- CMSIS core support comes from the official Arm `CMSIS_5` package
- startup, linker, and OpenOCD glue are kept local and minimal

Current assumptions:

- flash: `64 KiB`
- SRAM: `20 KiB`
- debug probe: Raspberry Pi Pico 2 running `debugprobe` firmware over `SWD`

The current `blink` project assumes a common `Blue Pill` style board with the user LED on `PC13` and active-low drive.
