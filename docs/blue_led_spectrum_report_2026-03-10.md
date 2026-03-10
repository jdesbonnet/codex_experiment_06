# Blue LED Spectrum Report (2026-03-10)

## Setup
- Spectrometer port: `/dev/ttyUSB0`
- DPS-150 current limit: `1.250 mA`
- DPS-150 measured LED voltage: `2.6828 V`
- DPS-150 measured LED current: `1.250 mA`
- DPS-150 measured LED power: `3.354 mW`
- Background frames averaged: `24` (frame IDs `5` to `28`)
- Illuminated frames averaged: `24` (frame IDs `50` to `73`)

## Result
The plot below shows the background-subtracted LED spectrum using the wavelength calibration polynomial from:
- `https://github.com/jdesbonnet/hamamatsu_c12880ma/blob/master/README.md`

Calibration applied:
- `lambda(i) = A0 + B1*i + B2*i^2 + B3*i^3 + B4*i^4 + B5*i^5`
- `A0=312.0790493`
- `B1=2.681652834`
- `B2=-8.061777879e-04`
- `B3=-1.052906745e-05`
- `B4=1.925845957e-08`
- `B5=-7.465510101e-12`

Peak response:
- Pixel: `74`
- Wavelength: `502.40 nm`
- Background-subtracted counts: `862.125`

![Background-subtracted blue LED spectrum](results/blue_led_spectrum_1p25ma.svg)

Raw data:
- Combined CSV: `results/blue_led_spectrum_1p25ma.csv`
