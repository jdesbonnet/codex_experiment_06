# CY8CKIT-049-42xx Notes

## Observed On This Host

Current USB enumeration:

- USB VID:PID: `04b4:0002`
- manufacturer: `Cypress Semiconductor`
- product: `USB-Serial (Single Channel)`
- host serial node: `/dev/ttyACM2`
- stable serial symlink: `/dev/serial/by-id/usb-Cypress_Semiconductor_USB-Serial__Single_Channel_-if00`

This matches the CY8CKIT-049 board architecture: the on-board USB device is a USB-serial bridge, not a CMSIS-DAP/ST-Link style debugger.

## Board And MCU

The CY8CKIT-049-42xx kit guide states that this kit variant carries:

- board: `CY8CKIT-049-42xx`
- target MCU: `CY8C4245AXI-483`
- MCU family: `PSoC 4200`

Local references:

- `datasheets/PSoC4_CY8CKIT-049-42xx/CY8CKIT-049-4xxx_PSoC_4_Prototyping_Kit_Guide_001-90711_RevJ.pdf`
- `datasheets/PSoC4_CY8CKIT-049-42xx/CY8CKIT-049-42xx_Quick_Start_Guide_001-90837_RevA.pdf`
- `datasheets/PSoC4_CY8CKIT-049-42xx/PSOC_4200_Family_Datasheet_001-87197_RevL.pdf`
- `datasheets/PSoC4_CY8CKIT-049-42xx/PSoC_4100_4200_Architecture_TRM_001-85634_RevH.pdf`

## Programming Paths

### 1. On-board USB serial bootloader

This is the default path shipped with the kit, assuming the resident bootloader is still present.

Key facts from the kit guide:

- the board is programmed through the USB-serial device using the bootloader host
- the PSoC 4 device must contain the bootloader
- the application project must be built as a bootloadable image
- the bootloadable build output used by the host is a `.cyacd` file
- to enter bootloader mode on the default kit image:
  - hold `SW1` while plugging the board in
  - the blue LED blinks rapidly when bootloader mode is active
- default UART bootload settings on this kit:
  - `115200` baud
  - `8` data bits
  - `1` stop bit
  - `no parity`

The detailed UART bootloader host/protocol reference is:

- `datasheets/PSoC4_CY8CKIT-049-42xx/AN68272_UART_Bootloader.pdf`

Important implication for Linux:

- a native Linux flashing path is feasible over `/dev/ttyACM2`
- the host must speak the Cypress/Infineon UART bootloader protocol from `AN68272`
- the host sends a `.cyacd` bootloadable image, not a raw ELF/bin

### 2. External SWD programmer/debugger

The kit guide also documents a 5-pin programming header for external programming/debug.

Official board behavior:

- the kit itself does not include an on-board debugger
- debug/program via SWD is done with an external probe such as `MiniProg3`

For Linux on this machine, the useful finding is that the installed OpenOCD already includes:

- `/usr/share/openocd/scripts/target/psoc4.cfg`
- `/usr/share/openocd/scripts/interface/cmsis-dap.cfg`
- `/usr/share/openocd/scripts/interface/kitprog.cfg`

That means an external CMSIS-DAP SWD probe is worth trying before buying a vendor probe.

Practical implication:

- your Raspberry Pi Pico 2 debugprobe should be a plausible first SWD option for this target
- however, PSoC 4 reset handling is quirky, and `psoc4.cfg` explicitly notes reset/halt caveats
- if generic CMSIS-DAP proves unreliable for reset/halt or mass erase, a KitProg/MiniProg class probe is the known-good fallback

## What This Means For Us

There are two realistic Linux workflows:

1. `USB serial bootloader`
   Use the board exactly as plugged in now on `/dev/ttyACM2`, enter bootloader mode with `SW1`, and implement or reuse a UART bootloader host that sends `.cyacd` images.

2. `External SWD probe`
   Wire the board's programming header to an SWD debugger and use OpenOCD with `target/psoc4.cfg`.

The serial-bootloader path is the least wiring, but it depends on the resident bootloader image still being intact.

The SWD path is the more general path because it gives:

- full-chip recovery
- debug access
- the ability to replace the bootloader itself if needed

## Recommended Next Step

The most efficient next experiment is:

1. verify bootloader-mode entry on the current board
2. capture behavior on `/dev/ttyACM2`
3. if the default bootloader is present, implement a small Linux UART bootloader uploader for `.cyacd`

If you want debug access rather than only serial bootloading, the next practical step is to wire the Pico 2 debugprobe to the CY8CKIT-049 programming header and probe it with OpenOCD.

## Local Tooling

There is now a local UART bootloader host script:

- `tools/psoc4_bootloader.py`

It currently supports:

- `probe`: detect the resident UART bootloader and report silicon ID, silicon revision, and bootloader version
- `upload`: send a `.cyacd` bootloadable image over the UART protocol from `AN68272`

Examples:

```sh
python3 tools/psoc4_bootloader.py probe --port /dev/ttyACM2 --verbose
python3 tools/psoc4_bootloader.py upload build/app.cyacd --port /dev/ttyACM2 --verbose
```

Current observed behavior on this board:

- normal plug-in does not expose an active bootloader response
- the tool reports no valid bootloader response until the board is explicitly put into bootloader mode
- the documented entry sequence remains:
  - hold `SW1`
  - plug the board in
  - wait for the blue LED to blink rapidly
  - retry `probe`

Additional observed behavior on this particular board:

- even with repeated `30` second probe attempts during replug and button hold, the target did not answer the `Enter Bootloader` command
- passive reads on `/dev/ttyACM2` produced no spontaneous bootloader output
- practical conclusion: this board is not currently exposing the expected resident factory UART bootloader

## Internet Findings

The most relevant Linux-era findings are:

- `PSoC Creator` is the original toolchain used by most `CY8CKIT-049-42xx` examples, and it is Windows-only
- `ModusToolbox` supports Linux, but this older kit's factory flow and example material are still largely `PSoC Creator` oriented
- the `CY8CKIT-049` USB interface is just a USB-to-UART bridge; programming over USB requires a resident bootloader already programmed into the target MCU
- community guidance and OpenOCD discussions indicate that an external `SWD` probe is the correct recovery/debug path once the resident bootloader is absent or unknown
- there are archived getting-started materials online that include the original factory `UART_Bootloader.hex` and example projects for this kit

## Practical Conclusion

For this specific board in its current state, the best next path is:

1. use an external `SWD` probe such as the Pico 2 debugprobe
2. gain control of the `CY8C4245AXI-483` over `OpenOCD`
3. either:
   - flash a simple test image directly over `SWD`, or
   - restore a UART bootloader image so that the USB serial path becomes useful again

The UART bootloader tool is still worth keeping because it should become useful again if we restore a suitable bootloader image.

## Sources

Official product page:

- <https://www.infineon.com/evaluation-board/CY8CKIT-049-42XX>

Official kit guide:

- <https://www.infineon.com/assets/row/public/documents/cross-divisions/44/infineon-cy8ckit-049-4xxx-psoc-4-prototyping-kit-guide-usermanual-en.pdf?fileId=8ac78c8c7d0d8da4017d0ef17bd002cb>

Official quick-start guide:

- <https://www.infineon.com/dgdl/Infineon-CY8CKIT-049-42xx_PSoC_4_Prototyping_Kit_Quick_Start_Guide-UserManual-v01_00-EN.pdf?fileId=8ac78c8c7d0d8da4017d0ef13a5f02b5>

Official PSoC 4200 datasheet:

- <https://www.infineon.com/assets/row/public/documents/30/49/infineon-psoc-4-psoc-4200-family-datasheet-programmable-system-on-chip-psoc-datasheet-datasheet-en.pdf>

Official PSoC 4100/4200 architecture TRM:

- <https://www.infineon.com/assets/row/public/documents/cross-divisions/57/infineon-psoc-4100-4200-family-psoc-4-architecture-trm-additionaltechnicalinformation-en.pdf>

Official UART bootloader application note:

- <https://www.infineon.com/assets/row/public/documents/cross-divisions/42/infineon-an68272-psoc-3-psoc-4-psoc-5lp-and-psoc-analog-coprocessor-uart-bootloader-applicationnotes-en.pdf>

Additional references:

- PSoC Creator page: <https://www.infineon.com/design-resources/development-tools/sdk/psoc-software/psoc-creator>
- ModusToolbox software page: <https://www.infineon.com/design-resources/development-tools/sdk/modustoolbox-software>
- ModusToolbox programming tools page: <https://www.infineon.com/design-resources/development-tools/sdk/modustoolbox-software/modustoolbox-programming-tools>
- Infineon PSoC4 digital designs repo: <https://github.com/Infineon/PSoC4-MCU-Digital-Designs>
- DigiKey CY8CKIT-049 getting-started page: <https://forum.digikey.com/t/getting-started-with-psoc-4-prototyping-kits-cy8ckit-049/13139>
- Infineon community thread on CY8CKIT-049-42xx USB/UART behavior: <https://community.infineon.com/t5/PSOC-4/cy8ckit-049-42xx/td-p/337990>
- Infineon community thread on PSoC 4 support in OpenOCD: <https://community.infineon.com/t5/PSOC-4/PSoC4-support-in-OpenOCD/td-p/82209>
- Infineon community thread on MiniProg/OpenOCD compatibility: <https://community.infineon.com/t5/PSOC-4/Programming-CY8C4126AZI-S423-with-Miniprog3-and-OpenOCD/td-p/1010549>
