# tiny_vm Development Environment

Unified development environment for authoring, simulating, and debugging
`tiny_vm` bytecode programs. Architecture lives in
`docs/dev_env_proposal.md`.

## What's here

| Component        | Path                                | Status        |
| ---------------- | ----------------------------------- | ------------- |
| Source maps      | `tools/vm_cc.py --map`, `tools/vm_asm.py --map` | shipped |
| Host-side sim    | `tools/dev_env/sim/`                | shipped       |
| DAP server       | `tools/dev_env/dap/`                | shipped       |
| Theia IDE        | `tools/dev_env/theia/`              | shipped       |
| Helper scripts   | `tools/dev_env/scripts/`            | shipped       |

The simulator, DAP server, and source-map tooling are fully functional even
without installing Theia. The IDE is the convenience layer on top.

## Quick start (no IDE)

```sh
# Compile a tiny_vm program (with source map for debuggers)
./tools/vm_cc.py projects/tiny_vm/tests/count10.cvm.c -o /tmp/count10.bin --map

# Run it in the host-side simulator
./tools/dev_env/sim/cli.py /tmp/count10.bin

# Or attach a debugger via the DAP server
python3 tools/dev_env/dap/server.py            # auto port, TCP
python3 tools/dev_env/dap/server.py --stdio    # stdio (Theia/VS Code mode)
```

The simulator and DAP server are byte-exact mirrors of the on-MCU runtime
in `common/src/tiny_vm.c`. Every program under `projects/tiny_vm/tests/`
produces the same UART output in the sim as on hardware (verified by
`tools/dev_env/sim/test_sim.py`).

## Quick start (IDE)

```sh
tools/dev_env/scripts/install.sh    # one-time: node deps + theia build
tools/dev_env/scripts/serve.sh      # serves the IDE on 0.0.0.0:3000
```

Open `http://<host>:3000` in a browser. From inside Theia:

- Open a `.cvm.c` file from `projects/tiny_vm/tests/`.
- Run command `tiny_vm: Debug Current File in Simulator` (or `Run ...` for
  no stop-on-entry).
- Set source-line breakpoints by clicking the gutter.

Behind the scenes the extension:
1. Calls `tools/vm_cc.py --map` on the open file, writing
   `/tmp/tiny-vm-theia/<base>.bin{,.map}`.
2. Launches `python3 tools/dev_env/dap/server.py --stdio` as the debug
   adapter.
3. Speaks DAP to that subprocess, exposing source/asm/bytecode-level
   stepping and locals/stack/memory inspection.

## Repo layout

```
tools/dev_env/
  sim/                    # host-side bytecode VM
    tiny_vm_sim.py        # python port of common/src/tiny_vm.c
    host_calls.py         # mocked led_write / delay_ms / print_*
    sourcemap.py          # reads .map files from vm_cc.py --map
    cli.py                # run a .bin and print output
    test_sim.py           # unit + regression tests
  dap/                    # debug adapter
    handlers.py           # DapSession + SimBackend
    server.py             # TCP + stdio transports
    test_dap.py           # end-to-end client tests
  theia/                  # Theia browser application
    package.json          # npm workspace root
    tiny-vm-extension/    # the tiny_vm Theia extension
    browser-app/          # the Theia browser application bundle
  scripts/                # install / serve / smoke shell helpers
  README.md
```

## Running the test suites

```sh
# host-side compiler/assembler tests (now also cover --map)
python3 tools/test_vm_tools.py

# simulator unit + regression tests
python3 tools/dev_env/sim/test_sim.py

# DAP server end-to-end tests (spawns the server, drives it over TCP)
python3 tools/dev_env/dap/test_dap.py

# all of the above, plus a CLI sanity run on count10
tools/dev_env/scripts/smoke.sh
```

## UI end-to-end (Playwright)

`tools/dev_env/theia/e2e/blink-debug.spec.ts` drives the actual browser
IDE: it opens `projects/tiny_vm/demos/blink.cvm.c`, starts a debug session
through our extension, and verifies it can step through the source line by
line.

Run it after `install.sh` has completed:

```sh
cd tools/dev_env/theia
npx playwright test --project=chrome-system
```

Notes:
- The config uses the system Google Chrome at `/usr/bin/google-chrome`
  because Playwright's bundled Chromium does not ship a build for
  ubuntu26.04-x64. Override with `CHROME_PATH=/usr/bin/chromium` if you
  have something different.
- Playwright launches its own Theia server on port 3001 with the repo
  root as the workspace. Set `THEIA_PORT` to override.
- Per-step screenshots are saved under `e2e/snapshots/` so you can
  inspect what each F10 actually showed.

`smoke.sh` is the canonical "before you merge" check for changes to
anything under `tools/dev_env/` or to `tools/vm_cc.py` / `tools/vm_asm.py`.

## Source map format

`vm_cc.py --map` emits `<output>.map` JSON next to the bytecode:

```json
{
  "version": 1,
  "source": "projects/tiny_vm/tests/count10.cvm.c",
  "bytecode_size": 27,
  "entries": [
    { "pc": 0,  "line": 1, "col": 1, "kind": "stmt" },
    { "pc": 4,  "line": 2, "col": 1, "kind": "loop_head" },
    { "pc": 12, "line": 3, "col": 5, "kind": "stmt" }
  ],
  "locals": [
    { "slot": 0, "name": "i", "line": 1 }
  ]
}
```

`vm_asm.py --map` emits a smaller version without `locals` and `col`/`kind`
since the assembler does not see those.

## Deferred (v2)

Per `docs/dev_env_proposal.md` section 6 "Deferred milestones":

- IDE button for flashing and `vm_upload.py` to real hardware.
- Native MCU debugging from the IDE via
  `tools/web_debugger_backend/server.py`.
- Language Server features (real diagnostics, goto-def, hover) for
  `.cvm.c`.

These are designed for — see the `DebugBackend` protocol in
`tools/dev_env/dap/handlers.py`: adding a `HardwareBackend` later does not
require any DAP-layer changes.

## Troubleshooting

- "tiny-vm-extension not found" inside Theia: re-run `install.sh`; the
  workspace symlink may be stale.
- DAP session never stops: confirm `python3 tools/dev_env/dap/test_dap.py`
  passes; that exercises the same protocol the IDE uses.
- Source breakpoint not verified: confirm `--map` was used to produce the
  `.bin.map` file the adapter looked up.
