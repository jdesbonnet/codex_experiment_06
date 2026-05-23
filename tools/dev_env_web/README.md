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
| M3: in-browser DAP                     | not started |
| M4: Playwright e2e                     | not started (the Playwright **console capture** script is in place) |
| M5: hardening + docs + static-host build | not started |

## Layout

| Path        | Purpose                                                                                  |
| ----------- | ---------------------------------------------------------------------------------------- |
| `sim/`      | wasm tiny_vm simulator (Rust → wasm-pack). Bit-exact mirror of `tools/dev_env/sim/`.    |
| `extension/`| VS Code Web extension. Languages, commands, OPFS FileSystemProvider, opcode-table view. |
| `host/`     | Self-hosted VS Code Web dev instance (`@vscode/test-web`). Pins versions, holds the Playwright console-capture script. |
| `scripts/`  | `install.sh`, `serve.sh`, `console-capture.sh` — top-level entrypoints.                  |

## Quick start

```sh
tools/dev_env_web/scripts/install.sh    # one-time: npm + cargo + wasm-pack
tools/dev_env_web/scripts/serve.sh      # serves on http://localhost:3000/
```

Open **`http://localhost:3000/`** in Chrome/Edge. **Do not use
`http://127.0.0.1:3000/`** — see "Why localhost" below.

Inside the IDE:

- Open any `projects/tiny_vm/tests/*.cvm.c` → it should syntax-highlight.
- `F1` (command palette) → `tiny_vm: Open Opcode Table` → opens the
  bytecode reference in a webview.

### OPFS workspace

To exercise the browser-local persistent workspace (the v2 "no server-side
files" path):

1. `F1` → **`tiny_vm: Seed OPFS Workspace`** — copies the eight test
   programs + the blink demo + the project README from the workspace mount
   into OPFS (Origin Private File System, scoped to this origin).
2. `F1` → **`tiny_vm: Open OPFS Workspace`** — adds a second workspace
   folder backed by `tinyvm-opfs:/`. You can browse, edit, save inside it
   and the changes persist across reloads.

OPFS is sandboxed (the browser, not the host) so the IDE never touches
your disk for OPFS-backed files.

## Diagnosis

The Playwright-driven console capture is the canonical way to read
browser console errors:

```sh
tools/dev_env_web/scripts/console-capture.sh > /tmp/cc.jsonl
grep '"level":"error"' /tmp/cc.jsonl
```

JSONL output: `console`, `pageerror`, `requestfailed`, and HTTP `response`
events with status ≥ 400. Two known-harmless 4xx events you can ignore:

| URL pattern                                            | Why it's harmless                  |
| ------------------------------------------------------ | ---------------------------------- |
| `/static/devextensions/package.nls.json`               | We don't ship localization files.  |
| `marketplace.visualstudio.com/.../tiny-vm-local/tiny-vm` | VS Code pings the marketplace to check for updates; our dev extension correctly doesn't exist there. |

Anything else — particularly `Cannot activate extension`,
`Failed to load grammar`, `Failed to construct 'URL'`, or `No file system
provider found` — indicates a real problem. M2 hit all of these at
different points; the workarounds are inline-documented in
`scripts/serve.sh`.

## Why localhost, not 127.0.0.1

`@vscode/test-web` builds the extension-host iframe URL as
`${protocol}://{{uuid}}.${host}/static/build`. If `${host}` is an IP
literal, the templated URL ends up as `xyz.127.0.0.1:3000/...` which the
browser's URL parser rejects (`TypeError: Failed to construct 'URL'`).
The extension host then fails to start and a cascade of "No file system
provider" errors follows.

`scripts/serve.sh` binds `--host=localhost` so the templated hostname
becomes `xyz.localhost`, which Chrome treats as loopback by RFC 6761.
The bind is still loopback-only — no LAN exposure. See
`docs/vscode_proposal.md §1` on the deliberate "no LAN" choice.

## Security model

- The dev server binds **loopback only**. To reach it from another machine,
  use SSH port-forwarding (`ssh -L 3000:localhost:3000 user@host`).
- **OPFS is the only file storage** scoped to the browser's origin. The
  extension cannot read host files outside the workspace mount.
- **No `child_process`** is available in the Web Extension host — by
  architecture, not by feature stripping. Adding a "Terminal" panel later
  would require an explicit backend, which v1 does not provide.

Contrast with the Theia setup (`tools/dev_env/theia/`), where the
backend is a Node.js process with full filesystem and subprocess access.
The Theia and VS Code Web setups stand side by side; choose whichever
matches your threat model.

## Why the wasm sim works without rebuilding

`sim/pkg/` (the built wasm + JS glue) is committed. Static-only deploys
do not need Rust/cargo on the build host; `install.sh` will rebuild the
wasm only if the toolchain is present. M5 will harden this path with a
build script that produces a fully self-hostable static bundle.

## Tests

The wasm sim has full unit + regression tests:

```sh
cd tools/dev_env_web/sim/rust
cargo test
```

These run the wasm sim against every `.cvm.c` in
`projects/tiny_vm/tests/` and assert the output matches the hardware
regression's `expected_lines()`. This is the M1 acceptance bar; all
eight cases pass.

The TypeScript side (extension, OPFS provider, future DAP) does not yet
have tests beyond `npm run typecheck`. Playwright e2e is M4.
