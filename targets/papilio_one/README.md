# Papilio One

This target directory captures the current `Papilio One` bring-up state.

## Confirmed So Far

- USB interface: `FT2232` (`0403:6010`)
- Linux device nodes:
  - `/dev/ttyUSB0`
  - `/dev/ttyUSB1`
- `OpenOCD` JTAG access works on `FTDI channel 0`
- Observed FPGA JTAG IDCODE: `0x41c22093`
- That IDCODE matches `Xilinx XC3S500E`

## Toolchain

For `Spartan-3E`, the practical synthesis/place-route toolchain is still
`Xilinx ISE 14.7`.

Important constraint:

- `ISE 14.7` is only supported by Xilinx/AMD on `x86` / `x86-64`
- the Raspberry Pi 5 in this repository is `ARM64`
- so do not plan on a native supported install on this Pi

Recommended workflow:

1. build the bitstream on an `x86-64` host or VM using `ISE 14.7`
2. copy the resulting `.bit` file into this repository
3. use `OpenOCD` on the Pi to load it into the Papilio One FPGA over JTAG

### Official install path

AMD/Xilinx still hosts the `ISE Archive`, including:

- `ISE Design Suite 14.7` full installers
- `ISE Design Suite 14.7` split multi-file installers
- `ISE Design Suite 14.7` Windows 10 / Windows 11 package

The easiest current route is usually:

1. use an `x86-64` Windows machine or VM
2. download `ISE 14.7` from the official archive
3. install the full toolchain there
4. build `.bit` files there
5. program the board from the Pi using:

```sh
openocd -s /usr/share/openocd/scripts \
  -f targets/papilio_one/openocd/base.cfg \
  -c "init; pld load 0 path/to/design.bit; shutdown"
```

### Official references

- AMD/Xilinx `ISE Archive`:
  <https://www.xilinx.com/support/download/index.html/content/xilinx/en/downloadNav/vivado-design-tools/archive-ise.html>
- `ISE Design Suite 14` release notes / install guide (`UG631`):
  <https://www.amd.com/content/dam/xilinx/support/documents/sw_manuals/xilinx14_7/irn.pdf>

From `UG631`, the supported Linux targets are legacy `x86/x86-64` enterprise
distributions rather than modern `ARM64` systems. That is why this repository
uses the Pi mainly as the programming and measurement host, not as the ISE
build host.

## OpenOCD

Use:

```sh
openocd -s /usr/share/openocd/scripts \
  -f targets/papilio_one/openocd/base.cfg \
  -c "init; scan_chain; shutdown"
```

Expected output includes:

```text
JTAG tap: xc3s500e.tap tap/device found: 0x41c22093
```

To load a volatile bitstream into the FPGA:

```sh
openocd -s /usr/share/openocd/scripts \
  -f targets/papilio_one/openocd/base.cfg \
  -c "init; pld load 0 build/top.bit; shutdown"
```

Current example project:

- `projects/blink/papilio_one_verilog/`

## Notes

- The passive UART probe on `/dev/ttyUSB0` and `/dev/ttyUSB1` showed no
  traffic. UART usage is still unresolved.
- Historic Papilio documentation often describes one FTDI channel as UART and
  the other as JTAG. On this attached board, the observed working JTAG channel
  is `channel 0` from `OpenOCD`'s point of view.
