# CG32X033 Target Package

This target package covers the WCH `CG32X033` development board currently on
the bench.

Observed USB identity:

- VID:PID: `1a86:fe0c`
- Product: `CH32x035`
- Manufacturer: `wch.cn`
- Serial: `0123456789`
- Interfaces: USB CDC ACM plus HID
- Current host serial node observed as `/dev/ttyACM0`

The board is treated as a WCH `CH32X03x`-family target for the repo tooling.
`third_party/ch32fun` already has `CH32X033` / `CH32X035` build support, and
the platform convention is:

- C project sources live in `projects/<name>/cg32x033_c`
- each project has a local `Makefile` including
  `third_party/ch32fun/ch32fun/ch32fun.mk`
- use `TARGET_MCU ?= CH32X033` in project Makefiles unless a specific board
  package requires overriding it
- each project provides a local `funconfig.h`

Known current status:

- `tools/build.sh --target cg32x033 --lang c --project <name>` builds the
  project-local ch32fun Makefile.
- `tools/flash.sh --target cg32x033 --lang c --project <name>` calls ch32fun
  `cv_flash`, which uses `minichlink`.
- The attached board did not respond to read-only `minichlink` ISP probes
  while running its current USB CDC/HID firmware. Programming may require
  entering the WCH USB ISP bootloader mode first.

Rust support is not currently wired for this target.
