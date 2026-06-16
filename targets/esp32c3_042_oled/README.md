# ESP32-C3 0.42" OLED Target Notes

Bring-up notes for the **01space ESP32-C3 0.42-inch OLED** dev board
(AliExpress listing `1005009157602185`, also sold as "ESP32-C3 SuperMini
0.42 OLED"). MicroPython workflow, not Rust/OpenOCD.

First brought up: `2026-06-16T13:30Z`.

## IMPORTANT: host divergence

This board was set up on host **`T1650`** (Ubuntu 26.04 LTS, x86_64), **not**
the Raspberry Pi 5 documented as the default host in the top-level `AGENTS.md`.
The board is on `T1650`'s USB. Procedures below are portable, but the
`~/esp32c3_oled/` working copy and the installed `esptool`/`mpremote` live on
`T1650`.

## Board details (from `esptool` + bench)

- chip: `ESP32-C3` (QFN32), revision `v0.4`
- features: Wi-Fi, BT 5 (LE), single core, 160 MHz, RISC-V
- flash: `4 MB` embedded (XMC)
- crystal: `40 MHz`
- USB: built-in `USB Serial/JTAG`, VID:PID `303a:1001`
- serial console: `/dev/ttyACM0`
- MAC: `e8:3d:c1:9a:f0:24`

## Display

- 0.42-inch OLED, **SSD1306-compatible**, **72 x 40** visible pixels
- I2C address `0x3C`
- I2C pins: **SDA = GPIO5, SCL = GPIO6**
- onboard LED: GPIO8 · boot button: GPIO9

### Gotcha: the 72x40 column offset

The 72x40 panel is a **window inside the controller's 128x64 RAM**. Every
flush must be shifted right by **28 columns** (`(128-72)/2`) and the MUX ratio
set to 39, or text lands off-screen. The stock upstream `ssd1306` driver does
*not* do this (and is not even bundled in the firmware). Use the local
`ssd1306_42.py` in this directory, which bakes in `XOFFSET=28` and
`MUX_RATIO=39`. If text is shifted by a couple of pixels on a given panel, try
`XOFFSET=30` or `26`; if mirrored/upside-down, flip `SET_SEG_REMAP` /
`SET_COM_OUT_DIR`.

## Firmware

- MicroPython **`v1.28.0`** (`ESP32_GENERIC_C3-20260406-v1.28.0.bin`)
- from <https://micropython.org/download/ESP32_GENERIC_C3/>
- the factory image is a vendor LED-cycle demo that spams the serial port
  (`[Close IO0 Led] AND [Open IO1 Led] ...`); flashing MicroPython replaces it

## Toolchain setup (host T1650, one-time)

`python3.14-venv` is **not** installed and `python3 -m venv` fails (no
`ensurepip`). Avoided sudo by installing `esptool` user-level:

```bash
pip3 install --user --break-system-packages esptool   # -> ~/.local/bin/esptool (v5.3.0)
# mpremote was already present at /usr/bin/mpremote
```

(`uv` is available at `~/.local/bin/uv` and would be a cleaner alternative if a
venv is wanted later.)

## Flash procedure

esptool auto-resets the C3 over USB-Serial/JTAG — no BOOT-button dance needed.

```bash
cd ~/esp32c3_oled   # on T1650
~/.local/bin/esptool --chip esp32c3 --port /dev/ttyACM0 erase-flash
~/.local/bin/esptool --chip esp32c3 --port /dev/ttyACM0 --baud 460800 \
    write-flash -z 0x0 ESP32_GENERIC_C3-20260406-v1.28.0.bin
```

esptool v5 uses hyphenated subcommands (`erase-flash`, `write-flash`).

## Day-to-day workflow (mpremote)

```bash
mpremote connect /dev/ttyACM0 repl              # live REPL, Ctrl-X to exit
mpremote connect /dev/ttyACM0 fs cp main.py :main.py   # upload (runs on boot)
mpremote connect /dev/ttyACM0 fs cp ssd1306_42.py :ssd1306_42.py
mpremote connect /dev/ttyACM0 run main.py       # run a local file without persisting
mpremote connect /dev/ttyACM0 fs ls             # list board filesystem

# quick I2C sanity check (should print ['0x3c'])
mpremote connect /dev/ttyACM0 exec \
  "from machine import Pin,I2C; print([hex(a) for a in I2C(0,scl=Pin(6),sda=Pin(5)).scan()])"
```

## Files in this directory

- `ssd1306_42.py` — offset-aware SSD1306 driver for the 72x40 panel
- `main.py` — hello-world (border rect + 3 text lines), runs on every boot

Both are also flashed to the board's filesystem (`boot.py` is the stock
MicroPython one). The live working copy on T1650 is `~/esp32c3_oled/`, which
also holds the firmware `.bin`.
