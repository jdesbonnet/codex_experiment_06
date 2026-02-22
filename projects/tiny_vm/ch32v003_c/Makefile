TARGET := tiny_vm
TARGET_MCU ?= CH32V003
TARGET_EXT := c

ADDITIONAL_C_FILES += ../../../common/src/tiny_vm.c
EXTRA_CFLAGS += -I../../../common/include

include ../../../third_party/ch32fun/ch32fun/ch32fun.mk

all: build
flash: cv_flash
clean: cv_clean
