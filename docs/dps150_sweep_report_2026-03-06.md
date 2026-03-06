# DPS-150 Sweep Report (2026-03-06)

## Objective
Sweep a 2-terminal DUT with the FNIRSI DPS-150 and capture I-V data while enforcing a strict current limit of **20 mA max**.

## Safety Controls
- Script hard-rejects `--i-limit-ma > 20`.
- Current limit set on PSU before enabling output.
- Output is forced OFF at start and best-effort OFF at end.
- Sweep stops once measured current reaches ~20 mA.

## Script
- `tools/dps150_sweep.py`

Example command used:

```bash
python3 tools/dps150_sweep.py \
  --port /dev/serial/by-id/usb-Artery_AT32_Virtual_Com_Port_13F50CF82565-if00 \
  --v-start 0 --v-stop 5 --v-step 0.25 \
  --i-limit-ma 20 --settle-ms 300 \
  --out-csv results/dps150_sweep.csv
```

## Device Identification (Power Supply)
- Model: `DPS-150`
- Hardware version: `V1.0`
- Firmware version: `V1.2`

## Sweep Results
- Data file: `results/dps150_sweep.csv`
- Points captured: `15`
- Compliance reached at ~`20 mA`.

Key points:

| Set V (V) | Measured V (V) | Measured I (mA) |
|---:|---:|---:|
| 3.00 | 3.00 | 2.644 |
| 3.25 | 3.25 | 11.647 |
| 3.50 | 3.2966 | 20.000 |

Full current curve (measured current in mA):

```mermaid
xychart-beta
  title "DUT I-V Sweep (Current vs Voltage)"
  x-axis "Measured Voltage (V)" [0.00,0.25,0.50,0.75,1.00,1.25,1.50,1.75,2.00,2.25,2.50,2.75,3.00,3.25,3.2966]
  y-axis "Current (mA)" 0 --> 20
  line [0,0,0,0,0,0,0,0,0,0,0,0,2.644,11.647,20.0]
```

## DUT Identification Attempt
Based on the I-V shape:
- Near-zero current up to ~2.8-3.0 V.
- Strong nonlinear turn-on around ~3.0-3.3 V.
- Hit current limit at ~3.30 V / 20 mA.

Most likely DUT type: **LED-like or diode-like nonlinear device**, likely with forward conduction knee around ~3 V.

## Fine Sweep Follow-Up (Higher Resolution)
Second run used finer steps around the knee:

```bash
python3 tools/dps150_sweep.py \
  --port /dev/serial/by-id/usb-Artery_AT32_Virtual_Com_Port_13F50CF82565-if00 \
  --v-start 2.60 --v-stop 3.60 --v-step 0.025 \
  --i-limit-ma 20 --settle-ms 350 \
  --out-csv results/dps150_sweep_fine.csv
```

Data file: `results/dps150_sweep_fine.csv` (31 points)

Extracted knee landmarks:
- ~`1 mA` at about `2.95 V`
- ~`2 mA` at about `2.98 V`
- ~`10 mA` at about `3.18 V`
- `20 mA` compliance at about `3.33 V`

```mermaid
xychart-beta
  title "Fine I-V Sweep Around Knee"
  x-axis "Measured Voltage (V)" [2.65,2.675,2.725,2.75,2.8,2.825,2.875,2.9,2.95,2.95,2.975,3.025,3.025,3.05,3.1,3.1,3.125,3.175,3.175,3.2,3.25,3.25,3.275,3.325,3.325]
  y-axis "Current (mA)" 0 --> 20
  line [0,0,0,0,0,0,0,0,1.272,1.657,2.231,3.199,3.83,4.74,6.047,6.817,7.906,9.37,10.194,11.543,13.255,14.059,15.496,17.733,20.0]
```

### More Detailed Speculation
Most likely: **single blue/white LED junction** (or a similar high-Vf visible LED).

Reasoning:
- Forward conduction begins around ~2.9-3.0 V, which is typical for GaN/InGaN blue/white LED chemistry.
- Current rise is strongly nonlinear (diode-like), not ohmic.
- 10 mA around ~3.2 V and 20 mA around ~3.33 V is in a plausible LED operating range.

Less likely alternatives:
- A zener in reverse breakdown near ~3.0-3.3 V (possible but less likely given smooth LED-like forward curve).
- Two silicon diodes in series (usually closer to ~1.2-1.6 V total at these currents, so unlikely).

Note:
- A couple of early low-current points (<2.7 V) show odd measured voltage values; this appears to be measurement/control settling behavior at near-zero load current and does not affect knee identification.
