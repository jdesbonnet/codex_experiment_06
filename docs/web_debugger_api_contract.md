# Web Debugger API Contract (MVP)

## Purpose

This document locks the concrete interfaces for Milestone 1 of the web debugger visualization project.

Scope for this contract:
- target: LPC1114 only
- backend language: Python
- transport to browser: HTTP + WebSocket
- debugger ownership: backend is the sole owner of OpenOCD and target-control actions

Out of scope for this contract:
- CH32V003 support
- multi-user concurrent control
- reverse proxying a full remote GDB server protocol
- high-rate streaming while target is running at full speed
- trace/SWO/RTT features

## MVP Process Model

The backend owns:
- starting and stopping the OpenOCD process
- opening and using the OpenOCD TCL command socket
- serializing all run-control requests
- polling registers and watched memory
- publishing state to browser clients

The browser owns:
- rendering state
- issuing user commands to the backend

The backend does not permit direct probe access by other tools during an active session.

## Backend State Machine

Session states:
- `disconnected`
- `connecting`
- `halted`
- `running`
- `error`

Allowed transitions:
- `disconnected` -> `connecting`
- `connecting` -> `halted`
- `connecting` -> `error`
- `halted` -> `running`
- `running` -> `halted`
- `halted` -> `disconnected`
- `running` -> `disconnected`
- any state -> `error`

Notes:
- the initial successful state after connect is `halted`
- reset requests may leave the target in either `halted` or `running`, but the backend must report the final state explicitly

## HTTP API (MVP)

Base path:
- `/api/v1`

### `POST /api/v1/session/connect`

Purpose:
- start OpenOCD and attach to the target

Request body:

```json
{
  "target": "lpc1114",
  "transport": "swd"
}
```

Response body:

```json
{
  "ok": true,
  "state": "halted"
}
```

### `POST /api/v1/session/disconnect`

Purpose:
- stop the session and release the probe

Response body:

```json
{
  "ok": true,
  "state": "disconnected"
}
```

### `POST /api/v1/target/run`

Response body:

```json
{
  "ok": true,
  "state": "running"
}
```

### `POST /api/v1/target/halt`

Response body:

```json
{
  "ok": true,
  "state": "halted"
}
```

### `POST /api/v1/target/step`

Request body:

```json
{
  "count": 1
}
```

Response body:

```json
{
  "ok": true,
  "state": "halted"
}
```

### `POST /api/v1/target/reset`

Request body:

```json
{
  "mode": "halt"
}
```

Allowed `mode` values:
- `halt`
- `run`

Response body:

```json
{
  "ok": true,
  "state": "halted"
}
```

### `GET /api/v1/target/registers`

Response body:

```json
{
  "ok": true,
  "arch": "armv6m",
  "registers": {
    "r0": "0x00000000",
    "r1": "0x00000000",
    "sp": "0x10001000",
    "pc": "0x00000124",
    "xpsr": "0x01000000"
  }
}
```

### `GET /api/v1/target/memory?address=0x10000000&length=64`

Response body:

```json
{
  "ok": true,
  "address": "0x10000000",
  "length": 64,
  "data_hex": "00112233445566778899aabbccddeeff..."
}
```

### `POST /api/v1/watch`

Purpose:
- add or replace a watched memory region for periodic publication

Request body:

```json
{
  "name": "vm_stack",
  "address": "0x10000000",
  "length": 64
}
```

Response body:

```json
{
  "ok": true
}
```

## WebSocket Stream (MVP)

Endpoint:
- `/ws`

Rules:
- server sends JSON text frames only for MVP
- every message contains `type` and `ts`
- `ts` uses ISO-8601 UTC with `Z` suffix

### Message: `session_status`

```json
{
  "type": "session_status",
  "ts": "2026-02-28T12:00:00Z",
  "state": "halted",
  "target": "lpc1114",
  "reason": "connected"
}
```

### Message: `register_snapshot`

```json
{
  "type": "register_snapshot",
  "ts": "2026-02-28T12:00:01Z",
  "arch": "armv6m",
  "seq": 42,
  "registers": {
    "r0": "0x00000001",
    "r1": "0x00000002",
    "r2": "0x00000003",
    "r3": "0x00000004",
    "r4": "0x00000005",
    "r5": "0x00000006",
    "r6": "0x00000007",
    "r7": "0x00000008",
    "r8": "0x00000009",
    "r9": "0x0000000a",
    "r10": "0x0000000b",
    "r11": "0x0000000c",
    "r12": "0x0000000d",
    "sp": "0x10001000",
    "lr": "0xffffffff",
    "pc": "0x00000124",
    "xpsr": "0x01000000"
  }
}
```

### Message: `memory_snapshot`

```json
{
  "type": "memory_snapshot",
  "ts": "2026-02-28T12:00:01Z",
  "seq": 42,
  "name": "vm_stack",
  "address": "0x10000000",
  "length": 16,
  "data_hex": "0102030405060708090a0b0c0d0e0f10"
}
```

### Message: `event`

```json
{
  "type": "event",
  "ts": "2026-02-28T12:00:02Z",
  "event": "breakpoint_hit",
  "pc": "0x00000124",
  "detail": "bkpt instruction"
}
```

### Message: `metrics`

```json
{
  "type": "metrics",
  "ts": "2026-02-28T12:00:02Z",
  "sample_hz": 10,
  "backend_latency_ms": 18,
  "dropped_frames": 0
}
```

### Message: `uart_rx`

```json
{
  "type": "uart_rx",
  "ts": "2026-02-28T12:00:03Z",
  "path": "/dev/ttyACM2",
  "text": "blink 42 PIO1_0=1\r\n"
}
```

## Sampling Policy (MVP)

Default modes:
- halted sampling: 10 Hz target
- running sampling: disabled by default

Rationale:
- halted-state sampling is deterministic and low-risk
- running-state sampling can perturb the target and is deferred until backend behavior is characterized

## Error Contract

HTTP errors:
- non-2xx on operational failure
- JSON body includes `ok: false`, `error`, and optional `detail`

Example:

```json
{
  "ok": false,
  "error": "probe_busy",
  "detail": "OpenOCD failed to claim the CMSIS-DAP interface"
}
```

WebSocket errors:
- emitted as `event` messages with `event: "error"`
- fatal backend failures are followed by a `session_status` update to `error`

## MVP Non-Goals

The following are deliberately excluded from the first implementation:
- CH32V003 or cross-target abstraction beyond field naming
- source-level symbol decoding
- disassembly view
- editable memory/register writes from the browser
- multiple frontends issuing independent control commands
- long-running historical recording or database storage
- exact protocol compatibility with a raw GDB remote server
- UART transmit from the browser

## Next Implementation Step

Once this contract is accepted, the next code step is:
- create a Python backend skeleton with the session state machine, stub HTTP endpoints, and a stub `/ws` publisher
