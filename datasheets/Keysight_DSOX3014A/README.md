# Keysight DSO-X 3014A

Local documentation for the `Agilent/Keysight DSO-X 3014A` (`InfiniiVision 3000 X-Series`).

## Files

- `9018-03427_InfiniiVision_3000_X-Series_User_Guide.pdf`
  - User guide for front-panel operation and general instrument use.
- `9018-06894_InfiniiVision_3000_X-Series_Programmers_Guide.pdf`
  - SCPI and remote-control programming guide.

## Linux control notes

On this Raspberry Pi, the scope enumerates through the kernel `usbtmc` driver as `/dev/usbtmc0`.

Current permissions observed during bring-up:
- device node: `/dev/usbtmc0`
- mode: `0600`
- owner/group: `root:root`

So remote control works through `USBTMC`, but access currently requires `root` unless a `udev` rule is added.
