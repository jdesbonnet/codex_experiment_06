# FNIRSI DPI-150 USB Protocol (Working Notes)

This page documents the currently known USB/serial protocol for the FNIRSI DPI/DPS-150 class device, based on public reverse-engineering sources.

Important:
- This protocol description is **not official**.
- It is derived from third-party reverse engineering and should be treated as provisional.
- The source project itself states the protocol is speculative.

## Source Basis

- Reverse-engineered implementation:
  - https://github.com/cho45/fnirsi-dps-150
- Reverse-engineered protocol summary in that repository README:
  - https://github.com/cho45/fnirsi-dps-150#protocol
- Reverse-engineered command/transport implementation:
  - https://github.com/cho45/fnirsi-dps-150/blob/main/dps-150.js
- Repository README (entry point + usage context):
  - https://github.com/cho45/fnirsi-dps-150/blob/main/README.md
- Vendor product page:
  - https://www.fnirsi.com/products/dps-150

Specific claims in this page are derived from those two source files unless explicitly noted otherwise.

## Transport

From `dps-150.js` in the reverse-engineered implementation:
- USB CDC ACM serial link
- baud: `115200`
- data bits: `8`
- parity: `none`
- stop bits: `1`
- flow control: `hardware`

On this host, `/dev/ttyACM2` currently enumerates as:
- `usb-Artery_AT32_Virtual_Com_Port_...`

## Frame Format

Request/response framing:
- `byte 0`: header
  - `0xF1` host -> device (output)
  - `0xF0` device -> host (input)
- `byte 1`: command
- `byte 2`: type
- `byte 3`: data length `N`
- `byte 4..(4+N-1)`: payload
- final byte: checksum

## Checksum

Checksum is 8-bit modulo sum of:
- `type`
- `length`
- all payload bytes

Equivalent formula:
- `checksum = (bytes[2] + bytes[3] + ... + bytes[n-1]) % 256`

## Command IDs

Observed command IDs:
- `0xA1` (`161`): get value
- `0xB0` (`176`): baud-related command
- `0xB1` (`177`): set value
- `0xC1` (`193`): session/connect command

## Typical Init Sequence

Observed startup command sequence in `initCommand()`:
1. session start (`CMD_SESSION`, payload `1`)
2. baud command (`CMD_BAUD`, payload index for 115200)
3. read model name
4. read hardware version
5. read firmware version
6. read all values (`type=255`)

## Data Types and Fields (Observed)

The reverse-engineered implementation maps many field IDs (examples):
- settable float fields:
  - voltage setpoint (`193`)
  - current setpoint (`194`)
  - protection thresholds (`OVP/OCP/OPP/OTP/LVP`)
- settable byte fields:
  - brightness (`214`)
  - volume (`215`)
  - metering enable (`216`)
  - output enable (`219`)
- info fields:
  - model name (`222`)
  - hardware version (`223`)
  - firmware version (`224`)
- bulk/all snapshot:
  - `type=255` returns a packed block containing many float/byte values

All float values are interpreted as little-endian IEEE-754 `float32`.

## Practical Notes

- Expect protocol/version drift across firmware revisions.
- Validate checksum and frame length strictly.
- Prefer a tolerant parser:
  - ignore unknown `type` values
  - keep command IDs/data offsets configurable
- Capture raw traffic when introducing new operations, then confirm decode assumptions before automating writes.

## Status in This Repo

This document is an external protocol reference for future integration work.

No production control code for this FNIRSI protocol has been added to this repository yet.
