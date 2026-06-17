# CG32X033 C BSP

Use ch32fun's `CH32X03x` support for startup, clocks, GPIO, USB, and linker
selection.

Project-level C ports should live under `projects/<name>/cg32x033_c` and set:

```make
TARGET_MCU ?= CH32X033
```

If a board-specific package variant is confirmed later, set
`TARGET_MCU_PACKAGE` in the project Makefile.
