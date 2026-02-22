# Agent Instructions


## Hardware setup:

You are running on a Raspberry Pi 5 running 64bit Raspberry Pi OS based on Debian Trixie.

Connected to the Raspberry Pi 5 via USB is a Raspberry Pi Pico 2 board running Raspberry Pi debugprobe firmware. The firmware currently in use is a custom `debugprobe_on_pico2` build with reset-line support enabled (`PROBE_PIN_RESET` on Pico 2 `GPIO1`). You will find documentation on the 3-pin interface in the datasheets directory file `raspberrypi-3pin-debug-spec.pdf` and general information at https://www.raspberrypi.com/documentation/microcontrollers/debug-probe.html. Keep in mind this is not the official Raspberry Pi Debug Probe hardware, but debugprobe firmware running on a Pico 2 board.

This debugger probe is connected to the target device: an LPC1114FN28/102 ARM Cortex-M0 chip (part of the LPC111X family) via the ARM Serial Wire Debug (SWD) port. The pinout of this chip is documented in fig 13 of the datasheet file `LPC111X.pdf` (in the datasheets directory). You will find information about programming it in file `UM10398.pdf`. There is no external crystal for timing, so you will be using the internal oscillator.

In addition to SWD and UART, there is now a dedicated reset wire from Pico 2 `GPIO1` (physical pin 2) to LPC1114 `nRESET` (`RESET/PIO0_0`). This allows OpenOCD to control target SRST for reliable hardware reset pulses.

There is a Microchip 23LC1024 SRAM chip connected to it via pins: 
PIO0_2 (connected to 'CS' pin on 23LC1024 via white wire), 
PIO0_6 (connected to 'SCK' pin on 23LC1024 via green wire), 
PIO0_8 (connected to 'SO' pin on 23LC1024 via yellow wire), 
PIO0_9 (connected to 'SI' pin on 23LC1024 via blue wire).

There is a LED connected to PIO1_2. The other end of the LED is connected via a resistor to ground.

Otherwise there are no other peripherals.

## UART setup

UART0 is connected to the Raspberry Pi debugger probe UART and is visible on the Pi as `/dev/ttyACM0`.
Use 57600 baud, 8N1, no flow control.

## Software tools

You will find software to talk to the debugging probe here: https://github.com/openocd-org/openocd


## My code standards:

- For timestamps use ISO-6801 in UTC using the 'Z' suffix. For internal calculations Java ms epoch time is preferred. If resources are constrained and whole second resolution is acceptable then unix epoch time in seconds is acceptable.
- If performing calculations or implementing an algorithm it is important that references are documented in comments.
- During the development phase we will add plenty of logging (except where that logging might affect timing).


## Permission to perform actions without seeking confirmation

- Agent has permission to run openocd on target device.
- Agent has permission to open UART on /dev/ttyACM0 (or any /dev/ttyACMx device).
