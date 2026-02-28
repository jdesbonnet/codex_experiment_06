# Web Debugger Backend Skeleton

## Purpose

This directory contains the first backend implementation step for the web debugger visualization work.

Current status:
- HTTP API skeleton is implemented
- WebSocket endpoint skeleton is implemented
- LPC1114 target operations use a real OpenOCD process plus the Tcl socket
- register and memory reads are live OpenOCD queries
- halted-state background sampling now publishes register snapshots and watched memory snapshots over WebSocket
- running-state WebSocket traffic is metrics-only for now

## Run

```bash
python3 tools/web_debugger_backend/server.py
```

Default bind:
- `127.0.0.1:8765`

## Useful Endpoints

- `GET /api/v1/session`
- `POST /api/v1/session/connect`
- `POST /api/v1/session/disconnect`
- `POST /api/v1/target/run`
- `POST /api/v1/target/halt`
- `POST /api/v1/target/step`
- `POST /api/v1/target/reset`
- `GET /api/v1/target/registers`
- `GET /api/v1/target/memory?address=0x10000000&length=16`
- `POST /api/v1/watch`
- `GET /ws` (WebSocket upgrade)

## Next Step

Extend `tools/web_debugger_backend/server.py` with:
- explicit OpenOCD error classification and recovery
- optional GDB/MI integration or proxy layer once the single-owner control path is stable
