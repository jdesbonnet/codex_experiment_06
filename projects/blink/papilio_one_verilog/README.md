# Papilio One Blink (Verilog)

This is a minimal `blink` port for the `Papilio One` FPGA board.

## Assumptions

- Board: `Papilio One 500K`
- FPGA: `XC3S500E-VQ100-4`
- Clock source: onboard `32 MHz` oscillator on `P89`
- Output pin: `WA4` on Wing A, mapped to FPGA pin `P35`

This follows the historic Papilio "blink pin 4 on A" convention. If you plug a
`B/LED Wing` into Wing A, LED 4 should blink. Without a wing attached, probe
`WA4` directly.

## Files

- `blink.v` - top-level Verilog module
- `papilio_one_wa4.ucf` - pin and timing constraints
- `Makefile` - Xilinx ISE build flow plus volatile JTAG load

## Build

This project expects the legacy Xilinx ISE command-line tools:

- `xst`
- `ngdbuild`
- `map`
- `par`
- `bitgen`

Build:

```sh
make -C projects/blink/papilio_one_verilog
```

Load bitstream into FPGA RAM:

```sh
make -C projects/blink/papilio_one_verilog load
```

## Notes

- The bitstream load is volatile. Power cycling the board will remove it.
- This Pi does not currently have a Spartan-3E synthesis toolchain installed.
- `Xilinx ISE 14.7` is the practical build toolchain for this design, but it is
  an `x86/x86-64` toolchain, not a native `ARM64` Raspberry Pi toolchain.
- Build on an `x86-64` host or VM, then copy the `.bit` file here and use
  `make load` from the Pi.

## References

- LinkSprite Papilio pinouts page: `WA4` used as the canonical blink example.
- Papilio One complete constraint file references:
  - `clk` on `P89`
  - `W1A<4>` on `P35`
- Local docs:
  - `datasheets/Papilio_One/README.md`
  - `targets/papilio_one/README.md`
