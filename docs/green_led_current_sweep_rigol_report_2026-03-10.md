# Green LED Current Sweep Spectrum Report (2026-03-10)

## Method
- One averaged dark capture was taken with the LED off.
- A second dark capture was taken to estimate the subtraction noise floor.
- The LED was then swept upward in current and a background-subtracted spectrum was captured at each point.
- The sweep stopped on the first clipped spectrum (`illuminated_mean >= 1000` for at least one pixel) or at the requested maximum current.

## Noise Floor
- Dark-to-dark peak absolute difference: `2.083` counts
- Dark-to-dark RMS difference: `0.747` counts
- Detection threshold used: `6.250` counts

## Findings
- First detected spectrum: `2.300 mA` (peak `38.167` counts at `556.65 nm`).
- No clipped spectrum was reached in this sweep.
- Observed measured-current steps: `0.900, 1.000, 1.100, 1.200` mA

## Plot
![LED spectrum current sweep](results/green_led_current_sweep_rigol.svg)

## Data
- Summary CSV: `results/green_led_current_sweep_rigol_summary.csv`
- Spectra CSV: `results/green_led_current_sweep_rigol_spectra.csv`
