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

### Open-source alternative assessment

For `Papilio One` / `Spartan-3E`, there is no mature open-source bitstream flow
that I would currently rely on for normal development on this Raspberry Pi.

In practice:

- `Yosys` is useful as a synthesis front-end, but it is not a complete
  `Spartan-3E` build flow by itself.
- `nextpnr` does not provide a `Spartan-3E` backend.
- Programming tools such as `OpenOCD` or `xc3sprog` can load an existing
  bitstream, but they do not replace synthesis, place-and-route, and bitstream
  generation.

So the practical answer for this board remains:

1. build `.bit` files on an `x86-64` machine with `ISE 14.7`
2. load them from the Pi over JTAG

### Comparison: Sipeed Tang Nano 20K

If the goal is an FPGA board with a practical open-source flow on a Raspberry
Pi, the `Sipeed Tang Nano 20K` is in a much better position.

Relevant facts:

- the board uses a `Gowin GW2AR-LV18QN88C8/I7` FPGA
- `Project Apicula` explicitly lists `Tang Nano 20K` as supported
- `nextpnr` documents Gowin support through the `himbaechel` architecture
- `openFPGALoader` documents a `tangnano20k` board target

That means a realistic open-source flow for `Tang Nano 20K` is:

1. `yosys`
2. `nextpnr-himbaechel` with Gowin support
3. `gowin_pack` from `Apicula`
4. `openFPGALoader -b tangnano20k`

So the board-level conclusion is:

- `Papilio One`: good for legacy `Spartan-3E` work, but not a good match for a
  native Raspberry Pi open-source FPGA toolchain
- `Tang Nano 20K`: much better fit if the priority is an open-source flow that
  can realistically run on Linux and on a Pi-class host

### Box64 experiment on this Pi

There is now a partially working emulation path on this Raspberry Pi host:

- installed package: `box64-rpi4`
- installed amd64 runtime path:
  - `/usr/x86_64-linux-gnu/lib`
  - `/usr/x86_64-linux-gnu/lib64`
- verified by running an extracted Debian `amd64` `hello` binary under `box64`

Verification command:

```sh
cd /tmp
apt-get download hello:amd64
rm -rf /tmp/hello_amd64
mkdir -p /tmp/hello_amd64
dpkg-deb -x hello_*_amd64.deb /tmp/hello_amd64
BOX64_LD_LIBRARY_PATH=/usr/x86_64-linux-gnu/lib:/usr/x86_64-linux-gnu/lib64 \
  box64 /tmp/hello_amd64/usr/bin/hello
```

Observed result:

```text
Hello, world!
```

Interpretation:

- `x86_64` Linux command-line binaries can run under emulation on this Pi
- this makes `ISE 14.7` CLI experimentation plausible
- but `ISE` itself has not yet been staged or validated under `box64`

The next practical step is to obtain the Linux `x86_64` `ISE 14.7` installer or
an already-installed command-line tool tree and test `xst`, `ngdbuild`, `map`,
`par`, and `bitgen` one by one under `box64`

Helper script:

- `tools/papilio_ise_box64.sh`

Example usage once `ISE 14.7` is installed on an `x86_64` Linux filesystem tree:

```sh
./tools/papilio_ise_box64.sh --ise-root /opt/Xilinx/14.7/ISE_DS --check
./tools/papilio_ise_box64.sh --ise-root /opt/Xilinx/14.7/ISE_DS xst -h
```

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
