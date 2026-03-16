# Ultrasonic Ranger

This project is a GCC-native port of the legacy `LPC824_Ultrasonic_Ranger`
firmware that was originally built in LPCXpresso with LPCOpen.

Current scope:

- target: `LPC824`
- language: `C`
- build system: plain `arm-none-eabi-gcc` + `make`
- startup/linker/flash support: repo-local `targets/lpc824/`
- runtime dependencies: official NXP CMSIS device headers only

The migrated firmware keeps the original design intent:

- drive paired 40 kHz ultrasonic transmit pins with the SCT
- sample the receive amplifier on `ADC3`
- use DMA to capture `3 x 1024` ADC samples into SRAM
- stream captures over `USART0`

Legacy source of record:

- `LPC824_Ultrasonic_Ranger/src/LPC824_Ultrasonic_Ranger.c`
- `LPC824_Ultrasonic_Ranger/README.md`

Hardware assumptions carried over from the legacy project:

- `PIO0_0`  -> `USART0 RXD`
- `PIO0_4`  -> `USART0 TXD`
- `PIO0_14` -> debug pulse output
- `PIO0_15` -> transducer TX A
- `PIO0_9`  -> transducer TX B
- `ADC3`    -> receive amplifier output

Notes:

- The legacy LPCOpen calls were replaced with direct CMSIS register access.
- The old LPCXpresso-specific files such as `cr_startup_lpc82x.c`, `sysinit.c`,
  `crp.c`, and `mtb.c` are not used in the new build.
- The current GCC build assumes the existing repo `LPC824` target defaults:
  internal `12 MHz` IRC clock, no external crystal.
- LPC824 SRAM is tight for a `3072`-sample capture buffer, so the project build
  sets `__heap_size__=0` and `__stack_size__=0x200` in its linker flags.
- This port is intended to preserve the legacy behavior, but it still needs
  hardware validation on the original ultrasonic board.

Build:

```sh
make -C projects/ultrasonic_ranger/lpc824_c
```

Flash:

```sh
./tools/flash.sh --target lpc824 --lang c --project ultrasonic_ranger
```

Web viewer:

- `tools/ultrasonic_waveform_webapp/README.md`
- `python3 tools/ultrasonic_waveform_webapp/server.py`

UART protocol draft:

- `docs/ultrasonic_ranger_uart_protocol.md`
