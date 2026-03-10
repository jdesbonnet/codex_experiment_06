# Blue LED Spectrum Report (2026-03-10)

## Setup
- Spectrometer port: `/dev/ttyUSB0`
- DPS-150 current limit: `1.250 mA`
- DPS-150 measured LED voltage: `2.6788 V`
- DPS-150 measured LED current: `1.250 mA`
- DPS-150 measured LED power: `3.348 mW`
- Background frames averaged: `24` (frame IDs `1` to `24`)
- Illuminated frames averaged: `24` (frame IDs `46` to `69`)

## Result
The plot below shows the background-subtracted LED spectrum on the spectrometer's native pixel axis.
No wavelength calibration is applied here, so the horizontal axis is pixel index rather than nm.

Peak response:
- Pixel: `73`
- Background-subtracted counts: `855.542`

![Background-subtracted blue LED spectrum](results/blue_led_spectrum_1p25ma.svg)

Raw data:
- Combined CSV: `results/blue_led_spectrum_1p25ma.csv`
