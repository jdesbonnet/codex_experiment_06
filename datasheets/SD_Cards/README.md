# SD Card Notes

This directory holds SD-card-specific notes and reference links used by the
STM32F103C8 SPI bring-up work.

## Full-Size SD Card SPI Mapping

For a full-size SD card in SPI mode, the relevant card contact numbers are:

- `pin 1` = `CS` / `DAT3`
- `pin 2` = `DI` / `CMD` / `MOSI`
- `pin 5` = `CLK`
- `pin 7` = `DO` / `DAT0` / `MISO`

This matches the current STM32F103C8 wiring:

- `PA4` -> SD card `pin 1`
- `PA5` -> SD card `pin 5`
- `PA6` -> SD card `pin 7`
- `PA7` -> SD card `pin 2`

## References

- SanDisk OEM product manual, SPI command framing and pin assignment:
  `https://manuals.plus/m/a6e63eabd679398e3e870ed75ab55c597f850e85296b2bc7fd100ae45f73f987`
- Analog Devices AN-1443, SD card operation overview including SPI mode:
  `https://www.analog.com/en/resources/app-notes/an-1443.html`
- Elm-Chan MMC/SDC app note, practical SPI-mode initialization details:
  `https://elm-chan.org/docs/mmc/mmc_e.html`
