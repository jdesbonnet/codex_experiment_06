# Ultrasonic Waveform Web App

This is a separate single-page web app for viewing live ultrasonic ranger
captures in real time.

Current scope:

- local WebSocket serial bridge backed by `pyserial`
- direct browser access to a USB UART using the Web Serial API as fallback
- decode the LPC824 ultrasonic frame format
- send hybrid `AT`-style control commands over the same UART
- show a single oscilloscope-style waveform display
- support persistence-of-vision fading for recent traces
- support display-side `Time/Div` and `Y/Div (DN)` controls
- support light and dark lab-instrument themes
- keep the transport layer pluggable for later WebSocket or socket-bridge
  adapters

## Current frame format

The app expects the current LPC824 ultrasonic stream format used by both the
legacy and GCC-native firmware:

- each frame starts with `W `
- each 12-bit ADC sample is encoded as two printable 6-bit characters
- each frame ends with `\r\n`
- current firmware emits `3072` samples per frame

## Run

Use the local server. It serves the page and also exposes a local WebSocket
bridge to the UART, which is the recommended transport for the debugprobe.

```bash
python3 tools/ultrasonic_waveform_webapp/server.py
```

Default URL:

- `http://127.0.0.1:8787/`
- WebSocket bridge: `ws://127.0.0.1:8788/`

Useful options:

```bash
python3 tools/ultrasonic_waveform_webapp/server.py \
  --uart-port /dev/ttyACM0 \
  --uart-baud 230400 \
  --port 8787 \
  --ws-port 8788 \
  --verbose
```

## Browser support

Use a modern browser. Chromium/Chrome is still required if you want to try the
Web Serial fallback.

## Notes

- The UI can:
  - refresh current device configuration
  - stop streaming
  - apply signal selection (`waveform` vs `envelope`)
  - apply protocol transport encoding for waveform mode (`COMPACT`, `TEXT`, `BIN`)
  - apply `MODE`, `NSHOT`, `TXFREQ`, `TXCYCLES`, and `SRATE`
  - start capture with `ATGO`
- The display can:
  - switch between light and dark themes
  - adjust `Time/Div`
  - adjust `Y/Div (DN)`
  - show persistence with the last `N` traces fading out
- The recommended browser transport is `WebSocket (local backend)`.
- `Web Serial` is kept in the UI, but it is not the preferred path for the
  Pico debugprobe dual-CDC interface.
- Live plotting currently supports:
  - `COMPACT`
  - `TEXT`
- `ENV`
- `BIN` can be selected and sent to the device, but the browser app does not
  yet decode binary waveform frames.
- Future transport adapters should fit behind the same frontend source
  interface, rather than special-casing serial in the UI.
