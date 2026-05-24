# tiny_vm VS Code Web dev environment

Browser-only port of the development environment in `tools/dev_env/` (Theia),
using **VS Code for the Web** instead of Eclipse Theia. See
`docs/vscode_proposal.md` for the architecture and milestones; this README
is the user-facing entry point.

## Status

| Milestone                              | Status |
| -------------------------------------- | ------ |
| M1: wasm tiny_vm simulator             | shipped — `sim/` |
| M2: extension scaffold + OPFS provider | shipped — `extension/`, `host/`, `scripts/` |
| M3: in-browser DAP                     | shipped — `extension/src/browser/debugAdapter.ts` |
| M4: Playwright e2e                     | shipped — `e2e/blink-debug.spec.ts` |
| M5: hardening + docs + smoke           | shipped — `scripts/smoke.sh` + this README |

## Layout

| Path        | Purpose                                                                                  |
| ----------- | ---------------------------------------------------------------------------------------- |
| `sim/`      | wasm tiny_vm simulator (Rust → wasm-pack). Bit-exact mirror of `tools/dev_env/sim/`.    |
| `extension/`| VS Code Web extension. Languages, commands, OPFS FileSystemProvider, in-process DAP, compile-client. |
| `host/`     | Dev-time @vscode/test-web instance + the `compile-server.mjs` sidecar (`POST /api/compile`) + Playwright diagnostic scripts. |
| `e2e/`      | Playwright spec exercising the full open→compile→debug→step→stop flow. |
| `scripts/`  | `install.sh`, `serve.sh`, `smoke.sh`, `console-capture.sh` — top-level entrypoints. |

## Quick start

```sh
tools/dev_env_web/scripts/install.sh    # one-time: npm + (optional) cargo + wasm-pack
tools/dev_env_web/scripts/serve.sh      # serves on http://localhost:3000/ + compile API on :3001
```

Open **`http://localhost:3000/`** in Chrome/Edge.  Do **not** use
`http://127.0.0.1:3000/` — see "Why localhost" below.

Inside the IDE:

- Open any `projects/tiny_vm/tests/*.cvm.c` or
  `projects/tiny_vm/demos/blink.cvm.c` — it syntax-highlights as
  *tiny_vm C*.
- `F1` (command palette) → `tiny_vm: Open Opcode Table` → opens the
  bytecode reference in a webview.

### Debug a `.cvm.c` source

1. Open a `.cvm.c` file.
2. Click in the editor gutter (left of the line numbers) to set a
   breakpoint — a red dot appears.
3. `F1` → **`tiny_vm: Debug Bytecode in Simulator`**.
   The extension POSTs the source to `http://localhost:3001/api/compile`
   (the sidecar), receives bytecode + source-map, stages them in OPFS at
   `tinyvm-opfs:/.cache/<base>.bin{,.map}`, and launches a DAP session
   against the wasm sim. Execution stops on line 1 (or the first
   source-mapped line if the file starts with declarations).
4. Use the **debug toolbar** to step. **F5 cannot be used in browser**
   because it reloads the page; use the toolbar's continue button or
   `F1` → `Debug: Continue`. F10/F11/Shift+F11 (step-over/in/out) work
   directly.

The host calls (`led_write`, `delay_ms`, `print_u32`, `print_hex32`)
emit to the **Debug Console** as the program executes.

### Cloud projects

Persistent projects stored on the server (in dev: `~/.tinyvm-projects/`
on the host running `serve.sh`; in production: a real backend service
implementing the same `/api/projects/*` contract from
`tools/dev_env_web/host/openapi.yaml`).

1. `F1` → **`tiny_vm: New Cloud Project`**. Enter a name. The server
   creates the project, seeds a `hello.cvm.c` blink-loop starter, and
   the IDE opens that file.
2. Edit, `Ctrl+S` to save. The save goes through the
   `tinyvm-cloud:` FileSystemProvider and `PUT /api/projects/{id}/files/...`
   to disk.
3. Compile + debug the file in place via
   `tiny_vm: Debug Bytecode in Simulator` — the cloud file is read
   over HTTP, compiled, and run in the wasm sim.
4. Close the browser. Open it again. `F1` →
   **`tiny_vm: Open Cloud Project`** → pick the project from the
   list. The starter file re-opens with your edits.

See `docs/cloud_storage_proposal.md` for the architecture and the
Spring Boot migration plan.

### OPFS workspace

The Origin Private File System provider gives you browser-local persistent
storage — useful when there is no server-side mount.

1. `F1` → **`tiny_vm: Seed OPFS Workspace`** — copies the eight test
   programs + the blink demo + the project README from the workspace mount
   into OPFS (scoped to this origin).
2. `F1` → **`tiny_vm: Open OPFS Workspace`** — adds a second workspace
   folder backed by `tinyvm-opfs:/`. Edit, save (`Ctrl+S`), reload — your
   edits persist.

OPFS is sandboxed (browser, not host disk).

## Tests

```sh
tools/dev_env_web/scripts/smoke.sh
```

Runs, in order:

1. `cargo test` in `sim/rust/` — 11 unit + 8 regression tests asserting
   bit-for-bit parity with `tools/dev_env/sim/tiny_vm_sim.py` and the
   on-hardware regression's `expected_lines()`.
2. `npm run typecheck` + `npm run build` in `extension/` — TypeScript
   compile + esbuild bundle.
3. Curl `/api/health` on the compile-server (starts `serve.sh` if needed).
4. **Playwright e2e** (`e2e/blink-debug.spec.ts`) — drives the IDE
   end-to-end through the open → compile → debug → step → stop loop.

Sub-targets if you want individual pieces:

```sh
(cd tools/dev_env_web/sim/rust && cargo test)          # sim only
(cd tools/dev_env_web/extension && npm run typecheck)  # extension only
(cd tools/dev_env_web/e2e && npx playwright test)      # e2e only (needs serve.sh up or webServer auto-start)
```

## Diagnosis

The Playwright-driven console capture is the canonical way to read
browser console errors out-of-band:

```sh
tools/dev_env_web/scripts/console-capture.sh > /tmp/cc.jsonl
grep '"level":"error"' /tmp/cc.jsonl
```

JSONL output: `console`, `pageerror`, `requestfailed`, and HTTP `response`
events with status ≥ 400. Two known-harmless 4xx events you can ignore:

| URL pattern                                              | Why it's harmless |
| -------------------------------------------------------- | ----------------- |
| `/static/devextensions/package.nls.json`                 | We don't ship localization files. |
| `marketplace.visualstudio.com/.../tiny-vm-local/tiny-vm` | VS Code pings the marketplace to check for updates; our dev extension correctly doesn't exist there. |

Anything else — particularly `Cannot activate extension`,
`Failed to load grammar`, `Failed to construct 'URL'`, `No file system
provider found`, or `compile-server unreachable` — indicates a real
problem. The known M2/M3 gotchas are inline-documented in
`scripts/serve.sh`, `host/compile-server.mjs`, and
`extension/src/browser/debugAdapter.ts`.

There is also a more aggressive Playwright debug-probe and breakpoint-probe
under `host/`, used during development to bisect the M3 bugs (DAP race,
CORS subdomain reflection, IPv4/IPv6 dual-listen, missing `breakpoints`
contribution). They're committed for the next time something breaks
from the browser side.

## Why localhost, not 127.0.0.1

`@vscode/test-web` builds the extension-host iframe URL as
`${protocol}://{{uuid}}.${host}/static/build`. If `${host}` is an IP
literal, the templated URL ends up as `xyz.127.0.0.1:3000/...` which
the browser's URL parser rejects (`TypeError: Failed to construct 'URL'`).
The extension host then fails to start and a cascade of "No file system
provider" errors follows.

`scripts/serve.sh` binds `--host=localhost` so the templated hostname
becomes `xyz.localhost`, which Chrome treats as loopback by RFC 6761.
The bind is still loopback-only — no LAN exposure.

## Security model

The original v1 plan called for "no backend" (Q2 in the proposal,
suggesting Pyodide or shipped artifacts). That was reversed on
2026-05-24: the project is destined for cloud hosting, so the build
endpoint moved into v1.  Current shape:

- The **VS Code Web bundle** is served as static files by
  `@vscode/test-web` on port 3000 (dev) — equivalent to an S3+CDN in
  production. It can edit OPFS-backed files and arbitrary `vscode-test-web://`
  mounted files, but cannot spawn processes, read host files outside
  the mount, or invoke shell commands.  Web Extensions API does not
  expose `child_process`, `fs`, or `net` to the extension worker.

- The **compile-server sidecar** on port 3001 (dev) runs `python3
  tools/vm_cc.py` via `child_process` for each `/api/compile` request.
  It only exposes the compile endpoint; in production this becomes a
  cloud service with the same wire protocol.  Both servers bind
  loopback-only by default — to reach the IDE from another device,
  use SSH port-forwarding (`ssh -L 3000:localhost:3000 -L 3001:localhost:3001 user@host`).

- The **compile-server CORS allowlist** reflects any localhost-family
  Origin (so VS Code Web's `{{uuid}}.localhost` subdomains are
  accepted in dev).  Production deployments tighten this to the
  production frontend origin and add auth.

- **OPFS storage** is sandboxed to the browser origin.  Files written
  via the `tinyvm-opfs:` scheme cannot escape to the host disk.

Contrast with the Theia setup (`tools/dev_env/theia/`): there, the
backend is a Node.js process with full filesystem and subprocess
access — anyone who can reach the HTTP port has shell as the server
user.  In the VS Code Web setup, the extension host worker
fundamentally cannot reach the host fs even if you wanted it to; the
only host-side capabilities are whatever the compile-server exposes
(today: just compile).

## Architecture decisions

Recorded inline in `docs/vscode_proposal.md` §8. Headline calls:

- **Sim language: Rust → wasm-pack** (Q1, 2026-05-23).  30-50 KB
  output, fast startup, clean JS bridge.  Pyodide and emscripten
  considered and ruled out.
- **Compile path: backend API** (Q2, 2026-05-24).  Sidecar in dev,
  cloud-hosted in production.  Pyodide attempted; hit
  `importScripts is blocked` (a fundamental ES-module-worker
  limitation) and was abandoned.

## Why the wasm sim works without rebuilding

`sim/pkg/` (the built wasm + JS glue) is committed.  Static-only
deploys do not need Rust/cargo on the build host; `install.sh` will
rebuild the wasm only if the toolchain is present.  CI can verify
parity with `cargo test`; the committed pkg/ is purely a deployment
convenience.
