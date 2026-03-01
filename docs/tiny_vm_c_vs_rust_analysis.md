# `tiny_vm` C vs Rust Analysis

This note summarizes the current size and tradeoff differences between the C and Rust `tiny_vm` runtimes in this repository.

## Current Runtime Sizes

Measured from the currently built images:

| Target | Language | `text` | `data` | `bss` | Linked total (`dec`) | Flash image (`.bin`) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| LPC1114 | C | 5881 | 0 | 4 | 5885 | 5881 |
| LPC1114 | Rust | 10080 | 0 | 8 | 10088 | 10080 |
| CH32V003 | C | 4444 | 0 | 4 | 4448 | 4444 |
| CH32V003 | Rust | 15536 | 0 | 4 | 15540 | 15536 |

Practical implications:

- smallest current runtime: `CH32V003` C (`4444` bytes)
- largest current runtime: `CH32V003` Rust (`15536` bytes)
- `CH32V003` Rust uses about `94.8%` of the available 16 KB flash
- both LPC1114 variants are still comfortably below the project `<16 kB` target

## Observations

Rust adds a significant fixed overhead in the current implementation.

The gap is moderate on LPC1114:

- `10080` vs `5881`
- roughly `+4.2 kB`

The gap is much larger on CH32V003:

- `15536` vs `4444`
- roughly `+11.1 kB`

This is not surprising given the way the current ports are structured.

## Why Rust Is Larger

### 1. Full VM Reimplementation

The current Rust runtime does not reuse the compact C VM core.

Instead:

- C runtime uses:
  - `common/src/tiny_vm.c`
- Rust runtime uses:
  - `common/rust/src/tiny_vm.rs`

So the Rust build is compiling a second, independent interpreter implementation rather than wrapping the existing compact C core.

This is likely the single biggest structural reason for the size gap.

### 2. Rust `core` and Compiler Support

Even with `#![no_std]`, the Rust embedded build still pulls in:

- `core`
- compiler support routines
- target support code needed by generated Rust

On the CH32V003 Rust path this is especially visible because the build uses:

- nightly toolchain
- `-Z build-std=core`

That is still much heavier than a small hand-written C runtime on a 16 KB microcontroller.

### 3. Panic and Language Runtime Overhead

The project uses `panic-halt`, which is already the minimal practical direction, but Rust still carries some fixed support overhead compared with C.

Even when optimized:

- panic path scaffolding
- helper routines for arithmetic and indexing
- glue emitted by the compiler

can cost a noticeable amount on very small targets.

### 4. PAC / Register Access Cost

The Rust ports use PAC-generated register access APIs.

These are clearer and safer, but they are often larger than direct register-level C writes, especially on tiny MCUs where every few hundred bytes matter.

This is particularly relevant for:

- UART setup
- GPIO access
- polling loops

### 5. C Shim + Rust Static Library on CH32V003

The CH32V003 Rust path currently follows a:

- Rust static library
- linked into a small ch32fun C shim

pattern.

The C shim itself is small, but the overall linking model is still less compact than the pure C path.

### 6. Small MCU Flash Makes Fixed Costs Dominant

On very small devices, fixed overhead dominates quickly.

That is why:

- LPC1114 Rust is larger but still acceptable
- CH32V003 Rust is technically buildable, but leaves very little flash headroom

## Interpretation By Target

### LPC1114

Rust is viable on LPC1114 for `tiny_vm`.

The runtime is larger than C, but still well within the project size target and already validated on hardware.

This makes LPC1114 a practical platform for:

- feature parity work
- runtime experimentation
- cross-checking the Rust implementation against the C baseline

### CH32V003

Rust is currently a constrained proof-of-concept on CH32V003.

It builds, but the runtime is so close to the 16 KB flash limit that:

- there is little room left for growth
- further feature expansion will be difficult without size work

That makes CH32V003 Rust more fragile as a long-term default runtime.

## Best Options To Reduce Rust Size

### 1. Reuse the C VM Core From Rust

Highest-value option.

Keep target/platform glue in Rust if desired, but call into:

- `common/src/tiny_vm.c`

instead of maintaining a second full interpreter in:

- `common/rust/src/tiny_vm.rs`

Benefits:

- removes duplicated interpreter logic
- likely recovers a substantial amount of flash
- reduces risk of C vs Rust semantic drift

### 2. Avoid Heavy PAC Use on the Smallest Targets

On CH32V003 in particular, replacing some PAC-based setup code with simpler direct register access may reduce overhead.

This gives up some ergonomics, but can be justified on a 16 KB part.

### 3. Tighten Rust Size Settings Further

The Rust builds should continue to use aggressively size-focused release settings, for example:

- LTO enabled
- `codegen-units = 1`
- `panic = "abort"`
- symbol stripping where appropriate

Some of this is already effectively in place, but explicit review is still worthwhile.

### 4. Treat CH32V003 Rust As Experimental Unless Optimized

Given the current size, the pragmatic position is:

- LPC1114 Rust: usable
- CH32V003 Rust: interesting, but not yet the default recommendation

## Current Recommendation

For size-sensitive deployment:

- prefer C on CH32V003
- Rust is acceptable on LPC1114

If the goal is to make Rust more practical on the smallest targets, the best next step is:

1. prototype a Rust runtime that reuses the C `tiny_vm` core
2. remeasure all four variants
3. decide whether a full native Rust interpreter is worth the extra flash cost
