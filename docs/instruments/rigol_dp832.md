# Rigol DP832

## Purpose

Programmable laboratory power supply used for LED current sweeps and controlled DUT biasing.

## Linux Access

The DP832 is controlled through `USBTMC`, typically `/dev/usbtmc0` or another `/dev/usbtmc*` node depending on what else is connected.

If the node is permission-restricted, add a `udev` rule for the Rigol device on the target machine. The repository does not yet carry a fixed Rigol rule because the current workflow has relied on temporary direct access rather than a standardized host setup.

## Repo Tools

- `tools/rigol_dp832.py`
- `tools/sweep_led_spectra.py`

## Data Produced Using This Instrument

- `results/green_led_current_sweep_rigol_summary.csv`
- `results/green_led_current_sweep_rigol_spectra.csv`
- `results/green_led_current_sweep_rigol.svg`
- `results/green_led_current_sweep_rigol_inline.svg`
- `results/green_led_current_sweep_rigol_peak_labels.svg`
- `docs/green_led_current_sweep_rigol_report_2026-03-10.md`

## Notes

- Current scripts use a single channel and expect standard SCPI over USBTMC.
- If standardizing a fresh host setup later, capture the DP832 `VID:PID` with `lsusb` and add a repo `udev` rule similar to the Keysight and Siglent examples.
