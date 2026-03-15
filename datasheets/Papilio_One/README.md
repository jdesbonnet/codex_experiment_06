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
- Installed OpenOCD Spartan-3 support:
  `/usr/share/openocd/scripts/fpga/xilinx-xc3s.cfg`

## Observed Hardware

- USB interface: `FT2232` (`0403:6010`)
- FPGA JTAG IDCODE: `0x41c22093`
- Inference: `Xilinx XC3S500E`

## Repository Config

- `targets/papilio_one/openocd/base.cfg`
- `targets/papilio_one/README.md`
