# Hamamatsu C12880MA Spectrometer

## Purpose

Visible-light spectrometer used for LED spectrum capture and wavelength-calibrated plots.

## Current Connection Model

The spectrometer is front-ended by an Arduino-class device that streams one spectrum frame per line over UART.

Typical host-side port used in this repository:

- `/dev/ttyUSB0`

## Repo Tools

- `tools/capture_led_spectrum.py`
- `tools/sweep_led_spectra.py`

## Calibration

The current wavelength calibration used by repository tooling comes from:

- https://github.com/jdesbonnet/hamamatsu_c12880ma

The calibration is applied in:

- `tools/capture_led_spectrum.py`

## Notes

- This is a UART-streaming setup, not direct USB control of the bare `C12880MA`.
- The host tooling expects newline-terminated text frames.
