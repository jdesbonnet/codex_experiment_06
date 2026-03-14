This target scaffold supports `LPC824` devices using the official NXP device pack
headers and startup files, with shared Arm CMSIS core headers from
`targets/lpc8xx/c_bsp/include/`.

Current assumptions:
- build is configured for `CPU_LPC824M201JDH20`
- default clocking uses the internal `12 MHz` IRC
- the `blink` project assumes a user LED on `PIO0_12`, active-low

If your LPC824 board uses a different LED pin or polarity, update the blink
project's compile-time defaults in `projects/blink/lpc824_c/main.c`.
