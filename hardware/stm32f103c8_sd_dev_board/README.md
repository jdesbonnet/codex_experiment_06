# STM32F103C8 SD Dev Board

Initial KiCad 9 schematic for a small STM32F103C8T6 board.

## Assumptions
- Main system power is supplied externally at `3.3V`. No regulator stage is included yet.
- `CR2032` holder feeds `VBAT` only. It is not intended to power the whole board.
- `microSD` is wired in `SPI` mode.
- `USART1` is broken out on a dedicated header.
- `SWD` header is a simple 1x6 pin header carrying `3.3V`, `SWDIO`, `SWCLK`, `NRST`, `GND`, `SWO`.

## GPIO breakout subset
The dedicated GPIO header exports:
- `PA0`, `PA1`, `PA2`, `PA3`
- `PB0`, `PB1`
- `PB10`, `PB11`, `PB12`, `PB13`, `PB14`, `PB15`

## Board-specific fixed assignments
- `PA4` `SD_CS`
- `PA5` `SD_SCK`
- `PA6` `SD_MISO`
- `PA7` `SD_MOSI`
- `PA9` `USART1_TX`
- `PA10` `USART1_RX`
- `PA13` `SWDIO`
- `PA14` `SWCLK`
- `PB3` `SWO`
- `PC13` user LED, active low
- `PD0` and `PD1` `8MHz` crystal

## Notes
- `BOOT0` and `PB2/BOOT1` each have a 1x3 selector header plus a default pulldown.
- The schematic uses stock KiCad 9 symbols and footprints. Footprints are first-pass choices and should be reviewed before layout.
