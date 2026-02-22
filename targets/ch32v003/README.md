# CH32V003 Target Package

This directory holds CH32V003 target metadata and OpenOCD config.

Planned content:

- `target.toml`: target metadata
- `openocd/`: interface/target config
- `linker/`: linker script(s)
- `c_bsp/`: C startup, clock, UART, GPIO, sleep support
- `rust_bsp/`: Rust PAC/HAL wrapper

Current state:
- CH32 C app build/flash is enabled via `ch32fun` project directories at `projects/<name>/ch32fun`.
- `tools/build.sh --target ch32v003 --lang c --project <name>` calls the project-local ch32fun Makefile.
- `tools/flash.sh --target ch32v003 --lang c --project <name>` uses ch32fun `cv_flash` by default.
- OpenOCD-based image flashing remains available via `tools/flash.sh ... --image <elf|bin|hex>`.
