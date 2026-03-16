# Ultrasonic Waveform Web App

This is a separate single-page web app for viewing live ultrasonic ranger
captures in real time.

Current scope:

- direct browser access to a USB UART using the Web Serial API
- decode the LPC824 ultrasonic frame format
- send hybrid `AT`-style control commands over the same UART
- show both:
  - the latest waveform
  - a rolling overlay of recent waveforms
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

Use the local server so the page is served from `localhost`, which is required
for Web Serial in Chromium-based browsers.

```bash
python3 tools/ultrasonic_waveform_webapp/server.py
```

Default URL:

- `http://127.0.0.1:8787/`

## Browser support

Use a browser with Web Serial support, typically Chromium or Chrome.

## Notes

- The UI can:
  - refresh current device configuration
  - stop streaming
  - apply `MODE`, `NSHOT`, `FMT`, `TXFREQ`, `TXCYCLES`, and `SRATE`
  - start capture with `ATGO`
- Live plotting currently supports:
  - `COMPACT`
  - `TEXT`
- `BIN` can be selected and sent to the device, but the browser app does not
  yet decode binary waveform frames.
- Future transport adapters should fit behind the same frontend source
  interface, rather than special-casing serial in the UI.
