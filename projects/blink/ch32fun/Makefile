TARGET := blink
TARGET_MCU ?= CH32V003

# ch32fun expects <TARGET>.c in the current directory.
TARGET_EXT := c

include ../../../third_party/ch32fun/ch32fun/ch32fun.mk

all: build
flash: cv_flash
clean: cv_clean
