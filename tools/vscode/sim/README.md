# tiny_vm wasm simulator

Rust + wasm-bindgen port of `tools/theia/sim/tiny_vm_sim.py`, which is itself
a port of `common/src/tiny_vm.c`. The C runtime is the spec; any divergence
is a sim bug. See `docs/vscode_proposal.md` §5.1 for the architecture.

## Layout

| Path        | Purpose                                                      |
| ----------- | ------------------------------------------------------------ |
| `rust/`     | Rust crate (`tiny_vm_sim`). Pure-Rust core + wasm-bindgen wrapper. |
| `pkg/`      | wasm-pack output (`tiny_vm_sim_bg.wasm` + JS glue). **Committed** so static-only deploys do not need Rust. |
| `tests/`    | Reserved for `test_sim.ts` (M2 / early M3 — drives the wasm pkg from Node). |

## Build

```sh
cd tools/vscode/sim/rust
cargo test                                 # native unit + regression tests
wasm-pack build --release --target web --out-dir ../pkg
```

`wasm-pack` requires the `wasm32-unknown-unknown` target and the `wasm-pack`
binary. Install once:

```sh
rustup target add wasm32-unknown-unknown
cargo install wasm-pack
```

## Tests

- `rust/src/lib.rs` `mod tests`: opcode-level unit tests (`cargo test --lib`).
- `rust/tests/regression.rs`: full-pipeline regression. Compiles every
  `.cvm.c` under `projects/tiny_vm/tests/` with `tools/vm_cc.py` and asserts
  the wasm sim's stdout matches the same expected lines the on-MCU hardware
  regression (`tools/test_tiny_vm_hardware.py`) checks against. This is the
  M1 acceptance bar.

Run both:

```sh
cd tools/vscode/sim/rust
cargo test
```

## Host triple override

`/.cargo/config.toml` at the repo root defaults the build target to
`thumbv6m-none-eabi` (LPC1114 / Cortex-M0). This crate overrides that to
`x86_64-unknown-linux-gnu` via `rust/.cargo/config.toml` so `cargo test`
runs on the host rather than trying to cross-compile to a Cortex-M.

If you build on a different host architecture (e.g. aarch64 Linux, macOS),
update `rust/.cargo/config.toml` or pass `--target <your-host>` explicitly.
M5 may replace the hardcoded triple with an env-driven override.

## wasm-opt note

The Rust 1.95 compiler emits `memory.copy` (bulk-memory ops). wasm-pack's
bundled `wasm-opt` does not enable bulk-memory by default, so the
`[package.metadata.wasm-pack.profile.release]` section in `Cargo.toml`
passes `--enable-bulk-memory` through.

## JS-side bridge contract

The browser-side DAP server (`tools/vscode/extension/`, **M3**) will
talk to `WasmTinyVm`. Coroutine handshake for host calls:

1. JS calls `step()` or `run(budget)`.
2. If the bytecode hits `OP_HOST`, the sim reads the `host_id` byte, sets
   `pending_host_call`, and returns status `STATUS_HOST_PENDING = 3`.
3. JS reads `pending_host_id()`, pops arguments via `pop()`, executes the
   host-call side effects, optionally pushes a return value via `push()`,
   then calls `complete_host_call(rc)`.
4. If `rc < 0`, the sim halts with `STATUS_ERR_HOST`. Otherwise execution
   resumes on the next `step()` / `run()`.

This mirrors how `DefaultHostCalls.call()` in
`tools/theia/sim/host_calls.py` pops args off the vm itself.
