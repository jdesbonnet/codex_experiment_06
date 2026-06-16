# Hello-world for the 01space ESP32-C3 0.42" OLED (72x40, SSD1306 @ 0x3C).
from machine import Pin, I2C
from ssd1306_42 import SSD1306_42

i2c = I2C(0, scl=Pin(6), sda=Pin(5), freq=400000)
oled = SSD1306_42(i2c)

oled.fill(0)
oled.rect(0, 0, oled.width, oled.height, 1)   # border, confirms screen edges
oled.text("Hello!", 4, 3, 1)
oled.text("ESP32-C3", 4, 14, 1)
oled.text("v1.28.0", 4, 25, 1)
oled.show()
