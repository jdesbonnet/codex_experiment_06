# Ultrasonic Ranger UART Protocol

This document defines the proposed UART control and streaming protocol for the
`ultrasonic_ranger` project.

Status:

- `draft`
- transport-oriented only
- intended to work unchanged over:
  - direct UART
  - WebSocket bridge
  - TCP socket bridge

## Goals

- keep host commands easy to type and inspect in a terminal
- preserve the existing compact waveform stream format as the default
- support future configuration without introducing a heavy parser on the MCU
- avoid a Hayes-style command/data mode split

## Framing

- host commands are ASCII lines terminated by `\r\n`
- device responses are ASCII lines terminated by `\r\n`
- waveform frames are emitted according to the selected output format

Default UART settings:

- `230400`
- `8N1`
- no flow control

## Command Model

The device accepts `AT`-style commands.

Base commands:

- `AT`
- `ATI`
- `ATCFG?`
- `ATMODE?`
- `ATMODE=<value>`
- `ATNSHOT?`
- `ATNSHOT=<n>`
- `ATFMT?`
- `ATFMT=<value>`
- `ATTXFREQ?`
- `ATTXFREQ=<hz>`
- `ATTXCYCLES?`
- `ATTXCYCLES=<n>`
- `ATSRATE?`
- `ATSRATE=<hz>`
- `ATSAMPLES?`
- `ATGO`
- `ATSTOP`
- `ATDEFAULT`

Recommended mode values:

- `SINGLE`
- `NSHOT`
- `CONTINUOUS`

Recommended format values:

- `COMPACT`
- `TEXT`
- `BIN`
- `ENV`

## Response Model

Success responses:

- `OK`
- `+INFO: ...`
- `+CFG: ...`
- `+DONE: ...`

Error responses:

- `ERROR`
- `ERROR:BADARG`
- `ERROR:RANGE`
- `ERROR:BUSY`
- `ERROR:UNKNOWN`

The device may emit an informational banner on startup:

```text
+INFO: proto=1,target=LPC824,fw=ultrasonic_ranger
```

## Configuration

Default values should match current firmware behavior:

- `MODE=CONTINUOUS`
- `NSHOT=1`
- `FMT=COMPACT`
- `TXFREQ=40000`
- `TXCYCLES=1`
- `SRATE=500000`
- `SAMPLES=3072`
- `ENVSAMPLES≈246` at defaults

Suggested aggregate config query:

```text
ATCFG?
+CFG: mode=CONTINUOUS,nshot=1,fmt=COMPACT,txfreq=40000,txcycles=1,srate=500000,samples=3072,envsamples=246
OK
```

## Capture Semantics

### `MODE=SINGLE`

- `ATGO` captures one waveform
- after the frame is emitted, the device replies:

```text
+DONE: frames=1
```

### `MODE=NSHOT`

- `ATNSHOT=<n>` defines the number of captures
- `ATGO` captures `n` waveforms
- after the last frame is emitted, the device replies:

```text
+DONE: frames=<n>
```

### `MODE=CONTINUOUS`

- `ATGO` starts continuous capture and emission
- `ATSTOP` ends capture
- after stopping, the device replies:

```text
+DONE: stopped
```

## Output Formats

### `FMT=COMPACT`

This preserves the current stream format.

Frame layout:

- prefix: `W `
- payload: two printable 6-bit characters per 12-bit sample
- suffix: `\r\n`

Example:

```text
W FtKPNOP@RSRlR|...
```

Each sample is encoded as:

- byte 1: `((sample >> 6) & 0x3f) + '?'`
- byte 2: `(sample & 0x3f) + '?'`

This is the default format and should remain stable for viewer compatibility.

### `FMT=TEXT`

Human-readable debugging format.

Example:

```text
T seq=42 count=3072 123,125,129,140,...
```

This is intentionally verbose and not the preferred streaming mode.

### `FMT=BIN`

Compact binary framing for high-rate operation.

Recommended packet structure:

- magic: `0x55 0x57`
- version: `0x01`
- type: `0x01`
- sequence: `uint32_le`
- sample_count: `uint16_le`
- payload_len: `uint16_le`
- payload: packed sample data
- crc16: `uint16_le`

Important rule:

- while `FMT=BIN` streaming is active, do not interleave ASCII status lines with
  binary waveform packets
- emit `OK` before streaming starts and `+DONE` after streaming stops

### `FMT=ENV`

Envelope mode computes one envelope sample per ultrasound cycle on the MCU and
emits a compact ASCII-armored frame.

First implementation:

- algorithm: peak `abs(sample - 2048)` per ultrasound cycle
- output rate: one envelope sample per cycle
- default output count: about `246` envelope points per frame at
  `TXFREQ=40000` and `SRATE=500000`

Frame layout:

- prefix: `E `
- payload: two printable 6-bit characters per envelope sample
- suffix: `\r\n`

Example:

```text
E RfTnUs...
```

This is intentionally simple for the Cortex-M0+:

- no Hilbert transform
- no floating point
- no adaptive bias in the first version

## Recommended First Implementation Scope

The first implementation should include:

- `AT`
- `ATI`
- `ATCFG?`
- `ATMODE=<value>`
- `ATNSHOT=<n>`
- `ATFMT=<value>`
- `ATTXFREQ=<hz>`
- `ATTXCYCLES=<n>`
- `ATSRATE=<hz>`
- `ATGO`
- `ATSTOP`

The first implementation should keep:

- `FMT=COMPACT` as default
- current excitation and ADC defaults unchanged

## Notes

- This protocol uses `AT`-style command verbs, but it does **not** use a modem
  command/data escape model.
- Waveform streaming and command processing share the same line-oriented control
  channel.
- If configuration changes during `CONTINUOUS` mode are awkward on the MCU,
  firmware may require streaming to be stopped before applying `ATTX*`,
  `ATSRATE`, or `ATSAMPLES`.
