# LPC1114 Target Package

This directory contains target-specific assets for LPC1114:

- `target.toml`: target metadata used by `tools/build.sh` and `tools/flash.sh`
- `openocd/`: OpenOCD target configuration links/overrides
- `linker/`: target linker scripts (future migration path)
- `c_bsp/`: C board-support package (future migration path)
- `rust_bsp/`: Rust BSP crate (future migration path)

Current state:
- Active LPC1114 build/flash still uses existing root-level flow (`Makefile`, `flash_project.sh`, `openocd/base.cfg`).
- New target-aware scripts route LPC1114 requests to that existing flow to avoid breakage.
