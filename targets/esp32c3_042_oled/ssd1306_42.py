# SSD1306 driver for the 0.42" 72x40 OLED on the 01space ESP32-C3 board.
# The 72x40 visible panel is a window inside the controller's 128x64 RAM,
# so every flush is shifted right by XOFFSET=28 columns. MUX ratio is set
# to 39 (40 rows). I2C: SDA=GPIO5, SCL=GPIO6, addr 0x3C.
from micropython import const
import framebuf

SET_CONTRAST = const(0x81)
SET_ENTIRE_ON = const(0xA4)
SET_NORM_INV = const(0xA6)
SET_DISP = const(0xAE)
SET_MEM_ADDR = const(0x20)
SET_COL_ADDR = const(0x21)
SET_PAGE_ADDR = const(0x22)
SET_DISP_START_LINE = const(0x40)
SET_SEG_REMAP = const(0xA0)
SET_MUX_RATIO = const(0xA8)
SET_COM_OUT_DIR = const(0xC0)
SET_DISP_OFFSET = const(0xD3)
SET_COM_PIN_CFG = const(0xDA)
SET_DISP_CLK_DIV = const(0xD5)
SET_PRECHARGE = const(0xD9)
SET_VCOM_DESEL = const(0xDB)
SET_CHARGE_PUMP = const(0x8D)

WIDTH = const(72)
HEIGHT = const(40)
XOFFSET = const(28)  # (128 - 72) / 2


class SSD1306_42(framebuf.FrameBuffer):
    def __init__(self, i2c, addr=0x3C):
        self.i2c = i2c
        self.addr = addr
        self.width = WIDTH
        self.height = HEIGHT
        self.pages = HEIGHT // 8
        self.buffer = bytearray(self.pages * self.width)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.init_display()

    def write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytes((0x80, cmd)))

    def init_display(self):
        for cmd in (
            SET_DISP,                 # display off
            SET_MEM_ADDR, 0x00,       # horizontal addressing mode
            SET_DISP_START_LINE,
            SET_SEG_REMAP | 0x01,     # mirror columns (board orientation)
            SET_MUX_RATIO, HEIGHT - 1,
            SET_COM_OUT_DIR | 0x08,   # scan COM[N-1]..COM0
            SET_DISP_OFFSET, 0x00,
            SET_COM_PIN_CFG, 0x12,
            SET_DISP_CLK_DIV, 0x80,
            SET_PRECHARGE, 0xF1,
            SET_VCOM_DESEL, 0x30,
            SET_CONTRAST, 0xFF,
            SET_ENTIRE_ON,            # follow RAM
            SET_NORM_INV,             # non-inverted
            SET_CHARGE_PUMP, 0x14,    # internal charge pump on
            SET_DISP | 0x01,          # display on
        ):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(XOFFSET)
        self.write_cmd(XOFFSET + self.width - 1)
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.i2c.writeto(self.addr, b"\x40" + self.buffer)

    def poweroff(self):
        self.write_cmd(SET_DISP)

    def poweron(self):
        self.write_cmd(SET_DISP | 0x01)

    def contrast(self, value):
        self.write_cmd(SET_CONTRAST)
        self.write_cmd(value & 0xFF)
