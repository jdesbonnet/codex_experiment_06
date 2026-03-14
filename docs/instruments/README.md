# Instrument Notes

This directory collects per-instrument setup notes, local documentation links, Linux access details, and repository tooling entry points.

Use this index before re-discovering USB details or repeating setup work on a fresh Raspberry Pi OS install.

## Instruments

- `docs/instruments/siglent_sdm3065x.md`
  - Siglent `SDM3065X-SC` digital multimeter
- `docs/instruments/rigol_dp832.md`
  - Rigol `DP832` programmable lab power supply
- `docs/instruments/keysight_dsox3014a.md`
  - Agilent/Keysight `DSO-X 3014A` oscilloscope
- `docs/instruments/hamamatsu_c12880ma_uart.md`
  - Hamamatsu `C12880MA` spectrometer front-ended by an Arduino over UART
- `docs/instruments/fnirsi_dps150.md`
  - FNIRSI `DPS-150` / `DPI-150` USB power supply
- `docs/instruments/webcam_microscope.md`
  - USB webcam microscope

## Local Documentation

Also check:

- `datasheets/CATALOG.md`
- `datasheets/Siglent_SDM3065X/`
- `datasheets/Keysight_DSOX3014A/`

## Fresh OS Setup

For USBTMC instruments, expect `/dev/usbtmc*` nodes to default to restrictive permissions until `udev` rules are installed.

Currently documented `udev` rules in this repo:

- `tools/udev/99-keysight-usbtmc.rules`
  - Keysight `DSO-X 3014A`

The Siglent `SDM3065X` rule is documented in:

- `docs/instruments/siglent_sdm3065x.md`

After adding or changing a rule:

```sh
sudo cp <rule-file> /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```
