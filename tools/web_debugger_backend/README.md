# Web Debugger Backend MVP

## Purpose

This directory contains the currently implemented backend MVP for the web debugger visualization work.

Current status:
- HTTP API skeleton is implemented
- WebSocket endpoint skeleton is implemented
- LPC1114 target operations use a real OpenOCD process plus the Tcl socket
- register and memory reads are live OpenOCD queries
- halted-state background sampling now publishes register snapshots and watched memory snapshots over WebSocket
- debugprobe UART mirror RX is streamed over WebSocket when a UI client is connected
- running-state WebSocket traffic is metrics-only for now

## Run

```bash
python3 tools/web_debugger_backend/server.py
```

Default bind:
- `127.0.0.1:8765`

UI:
- open `http://127.0.0.1:8765/` for the minimal built-in frontend
- the UI now includes a UART RX panel fed from the debugprobe mirror CDC port

## Useful Endpoints

- `GET /api/v1/session`
- `GET /` (minimal HTML UI)
- `GET /api/v1/config`
- `GET /api/v1/watches`
- `POST /api/v1/session/connect`
- `POST /api/v1/session/disconnect`
- `POST /api/v1/target/run`
- `POST /api/v1/target/halt`
- `POST /api/v1/target/step`
- `POST /api/v1/target/reset`
- `GET /api/v1/target/registers`
- `GET /api/v1/target/memory?address=0x10000000&length=16`
- `POST /api/v1/watch`
- `POST /api/v1/config`
- `DELETE /api/v1/watch?name=<watch-name>`
- `GET /ws` (WebSocket upgrade)

## Implemented UI Features

- session state display
- connect/disconnect/run/halt/step/reset controls
- register table
- watched memory panel with changed-byte highlighting
- watch add/remove controls
- halted sample-rate control
- UART RX panel (pause/clear)

## Next Step

Extend `tools/web_debugger_backend/server.py` with:
- explicit OpenOCD error classification and recovery
- optional GDB/MI integration or proxy layer once the single-owner control path is stable

## UART Notes

- The backend auto-detects the debugprobe mirror UART using:
  - `tools/find_debugprobe_uart_ports.sh --env`
- The backend opens the mirror UART in RX-only mode at `57600 8N1`.
- To avoid serial-read contention, only one process should read a given `/dev/ttyACM*` device node.
- Recommended split:
  - backend/UI reads the mirror port
  - any manual terminal session uses the primary UART port
