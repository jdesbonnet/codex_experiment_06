# Papilio One

Local reference set for the `Papilio One` FPGA board.

## Local Documents

- `DS312_Spartan-3E_FPGA_Family_Data_Sheet.pdf`
  - Xilinx Spartan-3E family datasheet
- `UG332_Spartan-3_Generation_Configuration_User_Guide.pdf`
  - Xilinx Spartan-3 generation configuration guide
- `DS_FT2232C_Dual_USB_UART_FIFO_IC.pdf`
  - FTDI `FT2232C` datasheet
- `DS_FT2232D_Dual_USB_UART_FIFO_IC.pdf`
  - FTDI `FT2232D` datasheet
- `AN2232C-01_Command_Processor_for_MPSSE_and_MCU_Host_Bus_Emulation_Modes.pdf`
  - FTDI MPSSE application note

## Useful External References

- Gadget Factory Papilio One hardware guide:
  <https://papilio.cc/index.php?n=Papilio.PapilioOneHardwareGuide>
- Papilio quick start guide:
  <https://learn.linksprite.com/papilio/papilio-quick-start-guide/>
- AMD/Xilinx `ISE Archive`:
  <https://www.xilinx.com/support/download/index.html/content/xilinx/en/downloadNav/vivado-design-tools/archive-ise.html>
- AMD/Xilinx `ISE Design Suite 14` release notes / installation guide:
  <https://www.amd.com/content/dam/xilinx/support/documents/sw_manuals/xilinx14_7/irn.pdf>
- Installed OpenOCD Spartan-3 support:
  `/usr/share/openocd/scripts/fpga/xilinx-xc3s.cfg`

## Toolchain Note

For `Spartan-3E`, the practical bitstream-generation toolchain is
`Xilinx ISE 14.7`.

- it is an `x86/x86-64` toolchain
- it is not a native supported toolchain for this repository's `ARM64`
  Raspberry Pi host

Practical workflow:

1. build `.bit` files on an `x86-64` host or VM with `ISE 14.7`
2. copy the bitstream into this repository
3. load it from the Pi with `OpenOCD`

## Open-source Flow Assessment

For `Papilio One` / `Spartan-3E`, there is not currently a mature open-source
end-to-end bitstream flow that I would treat as the default development path on
this Raspberry Pi.

By contrast, a board such as the `Sipeed Tang Nano 20K` has a substantially
better open-source path:

- `Project Apicula` lists `Tang Nano 20K` support
- `nextpnr` documents Gowin support via `nextpnr-himbaechel`
- `openFPGALoader` documents a `tangnano20k` board target

So if the selection criterion is "open-source FPGA flow that works well on
Linux / Raspberry Pi", a modern Gowin board such as `Tang Nano 20K` is a much
better fit than `Papilio One`.

## Box64 Experiment Note

This Raspberry Pi host now has a working `Box64` test setup:

- package installed: `box64-rpi4`
- cross amd64 runtime installed under:
  - `/usr/x86_64-linux-gnu/lib`
  - `/usr/x86_64-linux-gnu/lib64`
- verified using an extracted Debian `amd64` `hello` binary

That does not prove `ISE 14.7` works yet, but it does prove the basic idea of
running Linux `x86_64` CLI tools under emulation on this Pi.

Repository helper:

- `tools/papilio_ise_box64.sh`

## Observed Hardware

- USB interface: `FT2232` (`0403:6010`)
- FPGA JTAG IDCODE: `0x41c22093`
- Inference: `Xilinx XC3S500E`

## Repository Config

- `targets/papilio_one/openocd/base.cfg`
- `targets/papilio_one/README.md`
