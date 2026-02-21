# Minimal LPC1114 (Cortex-M0) build using GNU Arm Embedded Toolchain.
# Assumes arm-none-eabi-* tools are in PATH.

PROJECT := lpc1114_min
BUILD_DIR := build
SRC_DIR := src
INC_DIR := include

CC := arm-none-eabi-gcc
OBJCOPY := arm-none-eabi-objcopy
SIZE := arm-none-eabi-size

CFLAGS := -mcpu=cortex-m0 -mthumb -Og -g -ffunction-sections -fdata-sections \
	-Wall -Wextra -Werror -std=c11
CFLAGS += -I$(INC_DIR)

LDFLAGS := -T linker/lpc1114.ld -nostartfiles -Wl,--gc-sections

SRCS := $(SRC_DIR)/startup.c $(SRC_DIR)/main.c
OBJS := $(SRCS:$(SRC_DIR)/%.c=$(BUILD_DIR)/%.o)

.PHONY: all clean

all: $(BUILD_DIR)/$(PROJECT).elf $(BUILD_DIR)/$(PROJECT).bin
	$(SIZE) $(BUILD_DIR)/$(PROJECT).elf

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/$(PROJECT).elf: $(OBJS)
	$(CC) $(CFLAGS) $(OBJS) $(LDFLAGS) -o $@

$(BUILD_DIR)/$(PROJECT).bin: $(BUILD_DIR)/$(PROJECT).elf
	$(OBJCOPY) -O binary $< $@

clean:
	rm -rf $(BUILD_DIR)
