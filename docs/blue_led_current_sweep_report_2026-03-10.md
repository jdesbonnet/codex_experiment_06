# Blue LED Current Sweep Spectrum Report (2026-03-10)

## Method
- One averaged dark capture was taken with the LED off.
- A second dark capture was taken to estimate the subtraction noise floor.
- The LED was then swept upward in current and a background-subtracted spectrum was captured at each point.
- The sweep stopped on the first clipped spectrum (`illuminated_mean >= 1000` for at least one pixel).

## Noise Floor
- Dark-to-dark peak absolute difference: `1.917` counts
- Dark-to-dark RMS difference: `0.776` counts
- Detection threshold used: `5.750` counts

## Findings
- First detected spectrum: `0.550 mA` (peak `7.083` counts at `463.06 nm`).
- First clipped spectrum: `1.050 mA` with `12` saturated pixels.
- Observed measured-current steps: `0.050, 0.450` mA

## Plot
![LED spectrum current sweep](results/blue_led_current_sweep.svg)

## Data
- Summary CSV: `results/blue_led_current_sweep_summary.csv`
- Spectra CSV: `results/blue_led_current_sweep_spectra.csv`