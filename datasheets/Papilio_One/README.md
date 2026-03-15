# Papilio One

Local reference stub for the `Papilio One` FPGA board.

Useful external references:

- Gadget Factory Papilio One hardware guide:
  <https://papilio.cc/index.php?n=Papilio.PapilioOneHardwareGuide>
- Installed OpenOCD Spartan-3 support:
  `/usr/share/openocd/scripts/fpga/xilinx-xc3s.cfg`

Observed hardware on the attached board:

- USB interface: `FT2232` (`0403:6010`)
- FPGA JTAG IDCODE: `0x41c22093`
- Inference: `Xilinx XC3S500E`

Repository config:

- `targets/papilio_one/openocd/base.cfg`
- `targets/papilio_one/README.md`
