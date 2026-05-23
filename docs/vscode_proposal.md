# VS Code Web Development Environment Plan

This is the execution plan for a parallel implementation of the `tiny_vm`
development environment using **VS Code for the Web** (the architecture
that powers `vscode.dev`). The existing Theia-based implementation under
`tools/dev_env/theia/` is **not removed**; this plan stands beside it.

**Why a second implementation:** the Theia browser app shipped in
`tools/dev_env/theia/` is a server-side IDE — it ships a Node.js backend
with full host access (file I/O, subprocess spawning, terminal). Anyone
who can reach its HTTP port has shell-as-the-server-user. That is fine
for a single-user dev box behind a firewall but is not a sound base for
a multi-user or internet-exposed environment.

VS Code Web's web-extension architecture is **sandboxed by construction**:
extensions run in a Web Worker with no `child_process`, no host `fs`, and
no terminal. The browser is the runtime; the server (if any) is a static
file host plus optional auth and storage APIs. This eliminates the shell
vector at the architecture level rather than by feature stripping.

**Implementation status:** _not started_. This document is the spec; an
implementing agent or human can pick it up.

## 1. Purpose and Scope

Goal: provide a unified development environment for authoring,
simulating, and debugging `tiny_vm` programs (`.cvm.c` source and `.vm`
assembly) in a **browser-only runtime**, with the same edit/debug ergonomics
as the existing Theia version but no host-side shell exposure.

In-scope for v1 (this plan):
- VS Code Web extension that registers `.cvm.c` and `.vm` languages,
  a `tiny-vm` debug type, and the equivalent commands.
- In-browser host-side simulator (WebAssembly), bit-exact mirror of
  `common/src/tiny_vm.c` and the existing Python sim.
- In-browser DAP implementation (TypeScript) wrapping the wasm sim.
- Source-map driven source-line, opcode, and bytecode-level stepping
  (reuses existing `.map` schema).
- Playwright e2e test against a self-hosted VS Code Web build that
  matches `tools/dev_env/theia/e2e/blink-debug.spec.ts` behaviour.
- Onboarding README; static-only hosting recipe.

Deferred to v2 (designed for, not built in v1):
- **Authentication**: reverse-proxy gate (oauth2-proxy / Cloudflare
  Access / Authelia) or a built-in OIDC provider.
- **Cloud project files**: `FileSystemProvider` backed by REST / S3 /
  GitHub. v1 uses OPFS or the File System Access API only.
- **WebUSB / WebSerial hardware flashing**: drive the WCH-Link's UART
  bridge from the browser and call `minichlink`-equivalent SWIO routines
  over WebUSB. The host-side `tools/flash.sh` path is the v1 fallback
  (and remains the canonical hardware path).
- **Language Server features**: real diagnostics, goto-def, hover for
  `.cvm.c`. v1 ships syntax highlighting only, same as the Theia version.

Explicit non-goals:
- Full MCU emulation in the browser. Hardware is the authoritative check.
- Multi-tenant SaaS hosting in v1. The static-hosting recipe is for a
  single-user / small-team dev setup; SaaS auth/storage is v2.
- A new bytecode compiler or assembler. `tools/vm_cc.py` and
  `tools/vm_asm.py` remain the source of truth. They run either as a
  small build endpoint or as a developer-side step that produces
  `.bin` + `.map` artifacts committed alongside source. See section 8.

## 2. Existing Components (Carries Over)

Everything below is reused unchanged or with cosmetic wrapping:

| Component        | Path                                       | Role in this plan                                   |
| ---------------- | ------------------------------------------ | --------------------------------------------------- |
| Source-map schema| `tools/vm_cc.py --map`, `tools/vm_asm.py --map` | Identical JSON consumed by the in-browser DAP    |
| `.cvm.c` language| (TextMate grammar from Theia extension)    | Copied across, language registration is identical   |
| Bytecode test cases | `projects/tiny_vm/tests/*.cvm.c`        | Source of truth for sim acceptance tests            |
| Native runtime   | `common/src/tiny_vm.c`, `common/include/tiny_vm.h` | The reference being matched bit-for-bit         |
| Expected output  | `tools/test_tiny_vm_hardware.py` `expected_lines()` | Same expectations now asserted in JS tests    |
| Smoke script glue| `tools/dev_env/scripts/smoke.sh` (Theia)   | Web equivalent at `tools/dev_env_web/scripts/`       |

What does **not** carry over:
- `tools/dev_env/sim/tiny_vm_sim.py` — replaced by a wasm sim.
- `tools/dev_env/dap/server.py` — replaced by an in-browser DAP class.
- `tools/dev_env/theia/tiny-vm-extension/` — replaced by a VS Code Web
  extension. The command names and UX are mirrored deliberately.

## 3. Architecture

```
Browser (all execution):                Server (optional, minimal):
  Monaco editor                           Static asset host (CDN)
  VS Code Web extension host              Build endpoint (vm_cc / vm_asm)  [optional]
  └─ tiny-vm-extension (Worker)           Auth proxy                       [v2]
       ├─ language contributions          Cloud file API                   [v2]
       ├─ debug adapter (in-process)
       │    └─ TinyVmSim (wasm)
       └─ FileSystemProvider
            ├─ OPFS (default)
            └─ File System Access API     [user-chosen folder]
```

Key principles:
- **No backend by default.** v1 can be served as static files (S3 +
  CloudFront, or any HTTP server). The build endpoint is optional and
  not required for opening, editing, and debugging files already
  committed with `.bin` + `.map` artifacts.
- **Sim is wasm, not Pyodide.** See section 8 for the decision. Net: a
  Rust or C port of the existing Python sim, compiled with
  wasm-bindgen / emscripten. The Python sim remains as the reference for
  the wasm port to be validated against.
- **DAP is in-process.** No TCP/stdio transport — the extension calls
  the wasm sim directly. This is the biggest structural change from the
  Theia version, where DAP is a subprocess.
- **The bytecode contract is unchanged.** `.bin` files produced by
  `vm_cc.py` and consumed by `common/src/tiny_vm.c` on hardware are the
  same `.bin` files consumed by the wasm sim. Source maps are the same
  JSON schema.

## 4. Repository Layout

All new code lives under `tools/dev_env_web/`:

```
tools/dev_env_web/
  sim/                          # wasm simulator
    rust/   (or  c/)            # source code for the wasm sim
    pkg/                        # built .wasm + .js glue (committed for static-only deploys)
    test_sim.ts                 # mirror of test_sim.py, runs the wasm pkg
  extension/                    # VS Code Web extension (TypeScript)
    src/
      browser/                  # web-extension entrypoint
        extension.ts            # activate() — Web Extensions API only
        commands.ts             # tinyVm.runInSim / debugInSim / ...
        debugAdapter.ts         # in-process DebugAdapter implementation
        sourcemap.ts            # reads .map JSON
        filesystem/
          opfs.ts               # FileSystemProvider over OPFS
          fsa.ts                # FileSystemProvider over File System Access API
      common/
        types.ts                # shared TS types
        opcodes.ts              # opcode table mirrored from projects/tiny_vm/README.md
    syntaxes/
      tiny-vm-c.tmLanguage.json # copied from Theia extension
      tiny-vm-asm.tmLanguage.json
    package.json                # web-extension manifest
  host/                         # the static VS Code Web build itself
    package.json                # pins @vscode/test-web or equivalent
    public/                     # index.html, product.json customizations
    scripts/build.sh            # produces a fully self-hostable static bundle
  e2e/
    blink-debug.spec.ts         # Playwright against the static host
  scripts/
    install.sh                  # node deps, sim build
    serve.sh                    # static file server on :3000
    smoke.sh                    # end-to-end one-shot check
  README.md                     # user-facing entrypoint mirroring tools/dev_env/README.md
```

The build endpoint for `vm_cc.py` / `vm_asm.py` (if we ship one) lives
**outside** this tree — it is an ordinary HTTP service, not part of the
static IDE bundle. v1 may ship without it (see section 8).

## 5. Component Specifications

### 5.1 Wasm Simulator (`tools/dev_env_web/sim/`)

Language choice: **Rust + wasm-bindgen** (recommended). Rationale:
- The CH32V003 / LPC1114 / TM4C runtimes are all C, but the existing
  reference for the sim is `tiny_vm_sim.py` — a high-level port. A Rust
  port matches both code styles cleanly and produces ~30-50 KB of wasm
  versus ~10 MB for Pyodide-and-Python.
- The existing Rust port of the on-MCU runtime lives at
  `projects/tiny_vm/lpc1114_rust/` — opcode-handling code can be cribbed
  with light edits.
- Output is wasm + a small JS wrapper (`pkg/`). It is committed so
  static-only deploys do not require Rust on the build host.

Acceptance: for every test case in `tools/test_tiny_vm_hardware.py`,
running the wasm sim with the corresponding `.bin` produces an output
sequence that matches `expected_lines()`. This is the same bar the
Python sim is held to, asserted in `test_sim.ts`.

Host-call set (matches the existing Python sim and on-MCU C runtime):
`HOST_LED_WRITE`, `HOST_DELAY_MS`, `HOST_UART_PRINTLN_U32`,
`HOST_UART_PRINTLN_HEX32`. The wasm sim does not actually delay on
`HOST_DELAY_MS` (returns immediately) — same behaviour as the Python sim.

### 5.2 Source Map (no new code)

Reuses the existing `.map` JSON emitted by `vm_cc.py --map` and
`vm_asm.py --map`. `tools/dev_env_web/extension/src/browser/sourcemap.ts`
is a TypeScript port of `tools/dev_env/sim/sourcemap.py` — same lookup
semantics (`pc -> line`, `line -> pc`, locals by slot).

### 5.3 In-Browser DAP (`tools/dev_env_web/extension/src/browser/debugAdapter.ts`)

Implements `vscode.DebugAdapter` (the in-process form) rather than the
network DAP protocol. The extension creates an adapter directly; there
is no transport.

Requests handled (subset of full DAP, matches the Theia version):

| Request                | Behaviour                                                              |
| ---------------------- | ---------------------------------------------------------------------- |
| `initialize`           | Returns capabilities: source breakpoints, instruction stepping, disassembly. |
| `launch`               | Loads `.bin` + `.map` via the active `FileSystemProvider`, instantiates the wasm sim with `stopOnEntry`. |
| `setBreakpoints`       | Maps source lines to PCs via the `.map`; rejects unmapped lines.       |
| `continue` / `pause`   | Runs the sim to next breakpoint / step limit / halt; `pause` is cooperative since we are single-threaded. |
| `next` / `stepIn` / `stepOut` | Source-line stepping via source map (`stepIn`/`stepOut` are no-ops in v1, no calls in this VM). |
| `stepInstruction`      | Single bytecode opcode. Surfaced as "Step Instruction".                |
| `disassemble`          | Returns assembly lines around a PC range, using the opcode table.      |
| `evaluate`             | Read-only locals/stack/memory expressions.                             |

Events: `output` (sim stdout, LED log), `stopped`, `terminated`.

Backend abstraction: `DebugBackend` interface with `step()`, `cont()`,
`setBreakpoints()`, `inspect()`. In v1 the only implementation is
`SimBackend(WasmTinyVm)`. In v2, a `WebSerialHardwareBackend` could speak
the same `TVM1` upload protocol to a chip over WebSerial — DAP layer
unchanged. (Same design as the Theia version's `HardwareBackend`.)

### 5.4 VS Code Web Extension (`tools/dev_env_web/extension/`)

Manifest constraints: this is a **web extension**, declared with
`"browser": "./dist/web/extension.js"` in `package.json` and no `"main"`.
Web Extensions cannot import Node built-ins (`fs`, `child_process`,
`net`); the bundler (esbuild or webpack) must be configured to fail loudly
if any imports leak in.

Contributions:
- **Languages**: register `tiny-vm-c` (`.cvm.c`) and `tiny-vm-asm` (`.vm`)
  with the TextMate grammars copied from the Theia extension.
- **Debug type**: register `tiny-vm` debug type with an in-process
  `DebugAdapterDescriptorFactory` returning the adapter from 5.3.
- **Commands** (names mirror the Theia extension where possible):
  - `tinyVm.compile`: in v1 this is "Re-run the build endpoint" if
    configured, otherwise it shows a message saying `.bin` artifacts
    must be committed (see section 8).
  - `tinyVm.runInSim` / `tinyVm.debugInSim`: same UX as Theia.
  - `tinyVm.stepInstruction`: visible in Debug toolbar.
  - `tinyVm.openOpcodeTable`: opens a webview rendering the opcode
    table — same content as the Theia version.
- **Views**:
  - "tiny_vm Stack" tree view
  - "tiny_vm Memory" hex view (read-only in v1)
  - "tiny_vm Host Log" output channel

### 5.5 Filesystem Providers (`tools/dev_env_web/extension/src/browser/filesystem/`)

Two providers in v1:
- **OPFS provider** (default): files live in the Origin Private File
  System, scoped to the IDE's origin. Persistent, sandboxed, no user
  permission prompt.
- **File System Access API provider**: user picks a directory at session
  start; files live on the user's local disk in that directory.
  Chromium-family browsers only in v1 (Firefox support is partial).

Both providers expose the same workspace shape — `projects/`,
`common/include/`, `docs/`. The OPFS provider is seeded from a starter
bundle (a `.tar` of the relevant subtree) on first run, so the IDE is
not empty.

Cloud-backed providers (REST / GitHub / S3) are v2.

### 5.6 Build, Install, and Run Glue

`tools/dev_env_web/scripts/install.sh`:
- checks Node 18+ and `wasm-pack` (or `cargo` + a wasm target)
- installs npm deps for `extension/`, `host/`, `e2e/`
- builds the wasm sim (`sim/`) and commits the artifact under `sim/pkg/`

`tools/dev_env_web/scripts/serve.sh`:
- launches a static HTTP server (`http-server`, `caddy`, or `python -m
  http.server`) over `tools/dev_env_web/host/dist/` on port 3000
- explicitly does **not** bind 0.0.0.0 by default; documented in the
  README how to expose if desired
- has no Node backend running

`tools/dev_env_web/scripts/smoke.sh`:
- runs `test_sim.ts` against the wasm pkg for every committed test case
- runs the Playwright e2e against `serve.sh` for the blink debug flow
- this is the canonical "before you merge" gate for `dev_env_web/`

## 6. Milestones

Estimates in "turns" to match the Theia plan. A turn is one
user-assistant exchange.

### Milestone 1 — Wasm Simulator (8-12 turns)

Scope:
- Port `tools/dev_env/sim/tiny_vm_sim.py` to Rust under
  `tools/dev_env_web/sim/rust/`.
- Add `host_calls.rs` with the four host call IDs from 5.1.
- Build to `sim/pkg/` via `wasm-pack`.
- Write `test_sim.ts` that runs every test case in
  `projects/tiny_vm/tests/` through the wasm sim and asserts the same
  output the Python sim produces.

Acceptance:
- `test_sim.ts` passes for `count10`, `primes1000`, `collatz_max`,
  `checksum8`, `crc32`, `rotate32`, `mem32`, `sha1_abc`.
- Wasm bundle size under 100 KB.

### Milestone 2 — VS Code Web Extension Scaffold (6-9 turns)

Scope:
- Set up `tools/dev_env_web/extension/` as a web extension package.
- Register `tiny-vm-c` and `tiny-vm-asm` languages; copy grammars.
- Implement the OPFS `FileSystemProvider` and seed with a starter
  workspace.
- One smoke command (`tinyVm.openOpcodeTable`) to verify the extension
  loads in a self-hosted VS Code Web instance.

Acceptance:
- `host/scripts/build.sh` produces a static bundle that serves with no
  Node backend.
- Visiting `localhost:3000` loads VS Code Web with the extension active,
  `.cvm.c` files syntax-highlighted, and the opcode-table command runs.

### Milestone 3 — In-Browser DAP (10-14 turns)

Scope:
- Implement `debugAdapter.ts` against the DAP request table in 5.3.
- Wire it to the wasm sim from M1 via the `SimBackend`.
- Source-map ingest in `sourcemap.ts`.

Acceptance:
- Manual: open `projects/tiny_vm/tests/count10.cvm.c`, set a source
  breakpoint, hit `Run And Debug`, observe step-line through the loop.
- Scripted: a debug-flow unit test under `extension/src/test/` that
  drives the adapter through `launch -> setBreakpoints -> continue ->
  stopped -> stepInstruction -> halt`.

### Milestone 4 — Playwright E2E (6-9 turns)

Scope:
- `tools/dev_env_web/e2e/blink-debug.spec.ts` parallels the Theia
  spec at `tools/dev_env/theia/e2e/blink-debug.spec.ts`: launches the
  static host, opens blink.cvm.c, steps through, asserts UI state and
  snapshots per step.
- Reuse the same system-Chrome path noted in the Theia README
  (`/usr/bin/google-chrome`).

Acceptance:
- E2E passes locally on the same Pi OS / Ubuntu 24.04 / 26.04 environments
  the Theia README documents.

### Milestone 5 — Hardening, Smoke, Docs (4-6 turns)

Scope:
- `tools/dev_env_web/scripts/smoke.sh` ties M1+M3+M4 into one command.
- `README.md` parallel to `tools/dev_env/README.md`, with the same
  "Quick start (no IDE) / Quick start (IDE) / Tests / Source map" sections.
- Add a "Security model" section explicitly stating what is and is not
  exposed (in pointed contrast to the Theia version).
- Update root `README.md` to point at both dev envs.

Acceptance:
- `smoke.sh` exits 0 on a clean clone after `install.sh`.
- A reader unfamiliar with the project can go from `git clone` to
  stepping through `count10` in their browser using only the README.

### Deferred (v2 milestones, designed-for not built)

- **D1: WebSerial / WebUSB hardware path.** Talk to the WCH-Link's USB-CDC
  UART from the browser via WebSerial; speak `TVM1`. Optionally drive
  the LinkE's SWIO programming endpoint via WebUSB to flash firmware.
  Eliminates the need for any host-side `flash.sh`.
- **D2: Auth and cloud storage.** OIDC at the proxy; FileSystemProvider
  for GitHub or a REST API. Required for any multi-user / SaaS hosting.
- **D3: Build endpoint.** Small HTTP service (Cloudflare Worker /
  Lambda / FastAPI) that runs `vm_cc.py --map` and `vm_asm.py --map` on
  uploaded source. Avoids committing `.bin` artifacts when sources are
  edited entirely in-browser.
- **D4: LSP features.** Real diagnostics, goto-def, hover for `.cvm.c`,
  hosted as a Web Extension language server.
- **D5: Native MCU debug.** WebUSB-backed `HardwareBackend` for the DAP
  abstraction; equivalent to the Theia v2 plan but without the
  server-side OpenOCD path.

## 7. Risks

- **Wasm sim vs C runtime drift.** Every change to
  `common/src/tiny_vm.c` opcode semantics now has *three* mirrors to
  update: C, Python sim, Rust/wasm sim. Mitigation: the test cases in
  `projects/tiny_vm/tests/` are the cross-check oracle; both sims must
  pass them before merge. The hardware regression suite remains
  authoritative for on-chip behaviour.
- **VS Code Web API churn.** The "web extension" surface has been
  stable for ~3 years but is less battle-tested than the Node API. Pin
  versions in `extension/package.json` and `host/package.json`.
- **Browser File System Access API gaps.** Firefox support is
  incomplete. Mitigation: OPFS works everywhere modern; FSA is the
  "advanced mode" for Chromium users only in v1.
- **`vm_cc.py` runs on Python, not in the browser.** Until D3 ships,
  editing source in-browser cannot produce a `.bin` without help.
  Mitigation: v1 ships with `.bin` + `.map` artifacts committed
  alongside each test case; the "edit and debug" loop works on the
  committed artifacts. Recompilation requires either a build endpoint
  or a local dev with Python.
- **Static-host caching gotchas.** A new wasm sim must invalidate
  caches; mitigate by content-hashing `sim/pkg/` filenames in
  `extension/package.json`.

## 8. Open Questions

1. **Sim implementation language: Rust vs C-via-emscripten vs Pyodide?**
   This plan assumes Rust. Decision drivers:
   - Pyodide: zero porting effort (we can ship `tiny_vm_sim.py` itself),
     but bundle is ~10 MB and startup is ~1-2 s.
   - C via emscripten: could compile `common/src/tiny_vm.c` directly,
     ensuring perfect parity with on-MCU C semantics. Build complexity
     is higher and tooling is heavier on Pi OS.
   - Rust: 30-50 KB wasm, fast startup, clean JS bridge, but requires a
     hand port. Recommended in this plan, but worth confirming.
2. **`vm_cc.py` in the browser?** Options:
   - Ship `.bin` artifacts committed alongside `.cvm.c` (zero browser
     work; awkward DX since "edit and run" requires either an external
     build step or D3).
   - Pyodide just for `vm_cc.py` (10 MB bundle for a 569-line script;
     overkill).
   - Port `vm_cc.py` to TypeScript (real work; possibly desirable since
     a TS port could provide LSP diagnostics for free in D4).
   - Build endpoint as a v1 dependency rather than v2.
3. **Hosting target.** Static-only on S3+CloudFront / Cloudflare Pages
   / GitHub Pages is the v1 default. Worth confirming this rather than
   self-hosting the static bundle on a Pi.
4. **Test-runner for `test_sim.ts`.** Vitest is the obvious choice
   (fast, web-friendly). Jest works but is slower in CI.
5. **Bundler.** esbuild vs webpack vs vite for the extension and host
   bundles. esbuild is fastest and matches what `@vscode/test-web` uses
   internally; recommended.
6. **Should this live in this repo or a sibling?** The Theia code is
   already a substantial subtree. Pros of same repo: shared tests,
   shared CI, single PR for cross-stack changes. Cons: bigger checkout,
   slower CI. Default in this plan: same repo, under `tools/dev_env_web/`.

## 9. Reference Files

Existing code this plan reads from:

- `docs/theia_proposal.md` — the original Theia plan; this doc mirrors
  its structure.
- `tools/dev_env/README.md` — the user-facing entry point being mirrored.
- `tools/dev_env/sim/tiny_vm_sim.py` — reference implementation for the
  wasm port.
- `tools/dev_env/dap/handlers.py` — reference for the DAP request set
  and the `DebugBackend` abstraction.
- `tools/dev_env/theia/tiny-vm-extension/` — reference for the command
  surface and UX.
- `tools/dev_env/theia/e2e/blink-debug.spec.ts` — reference Playwright
  flow.
- `tools/test_tiny_vm_hardware.py` `expected_lines()` — acceptance
  oracle for sim outputs.
- `projects/tiny_vm/README.md` — opcode table.
- `common/src/tiny_vm.c`, `common/include/tiny_vm.h` — authoritative VM
  semantics.
