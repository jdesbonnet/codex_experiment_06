# Common Protocol Helpers

Place hardware-agnostic protocol helpers here (SPI framing, UART message formats, etc.).

Rule:
- No direct register access in this layer.
- Target-specific peripheral access belongs in `targets/<mcu>/*_bsp`.
