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

## Notes

- The passive UART probe on `/dev/ttyUSB0` and `/dev/ttyUSB1` showed no
  traffic. UART usage is still unresolved.
- Historic Papilio documentation often describes one FTDI channel as UART and
  the other as JTAG. On this attached board, the observed working JTAG channel
  is `channel 0` from `OpenOCD`'s point of view.
