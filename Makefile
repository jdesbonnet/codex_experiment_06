# Multi-project LPC1114 build using GNU Arm Embedded Toolchain.
# Usage: make PROJECT=sram_test

PROJECT ?= sram_test
BUILD_DIR := build/$(PROJECT)

CC := arm-none-eabi-gcc
OBJCOPY := arm-none-eabi-objcopy
SIZE := arm-none-eabi-size

CFLAGS := -mcpu=cortex-m0 -mthumb -Og -g -ffunction-sections -fdata-sections \
	-Wall -Wextra -Werror -std=c11
CFLAGS += -Icommon/include

LDFLAGS := -T linker/lpc1114.ld -nostartfiles -Wl,--gc-sections

COMMON_SRCS := \
	common/src/startup.c \
	common/src/clock.c \
	common/src/systick.c \
	common/src/uart.c \
	common/src/ssp.c \
	common/src/sram23lc1024.c

PROJECT_SRC := projects/$(PROJECT)/main.c

OBJS := \
	$(COMMON_SRCS:%.c=$(BUILD_DIR)/%.o) \
	$(BUILD_DIR)/$(PROJECT_SRC:.c=.o)

.PHONY: all clean

all: $(BUILD_DIR)/$(PROJECT).elf $(BUILD_DIR)/$(PROJECT).bin
	$(SIZE) $(BUILD_DIR)/$(PROJECT).elf

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: %.c | $(BUILD_DIR)
	mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/$(PROJECT).elf: $(OBJS)
	$(CC) $(CFLAGS) $(OBJS) $(LDFLAGS) -o $@

$(BUILD_DIR)/$(PROJECT).bin: $(BUILD_DIR)/$(PROJECT).elf
	$(OBJCOPY) -O binary $< $@

clean:
	rm -rf build
