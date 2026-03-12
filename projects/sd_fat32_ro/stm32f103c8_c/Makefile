PROJECT := sd_fat32_ro
REPO_ROOT := ../../..
TARGET_DIR := $(REPO_ROOT)/targets/stm32f103c8
BUILD_DIR := build

CC := arm-none-eabi-gcc
OBJCOPY := arm-none-eabi-objcopy
OBJDUMP := arm-none-eabi-objdump
SIZE := arm-none-eabi-size

CFLAGS := -mcpu=cortex-m3 -mthumb -Og -g -ffunction-sections -fdata-sections
CFLAGS += -Wall -Wextra -Werror -Wshadow -std=c11
CFLAGS += -DSTM32F103xB
CFLAGS += -I$(TARGET_DIR)/c_bsp/include
CFLAGS += -MMD -MP

LDFLAGS := -T $(TARGET_DIR)/linker/stm32f103c8.ld -nostartfiles
LDFLAGS += -Wl,--gc-sections -Wl,-Map,$(PROJECT).map

OBJS := \
	$(BUILD_DIR)/main.o \
	$(BUILD_DIR)/startup.o \
	$(BUILD_DIR)/system_stm32f1xx.o

DEPS := $(OBJS:.o=.d)

OPENOCD_BIN ?= openocd
OPENOCD_SCRIPTS ?= /usr/share/openocd/scripts
OPENOCD_CFG ?= $(TARGET_DIR)/openocd/base.cfg

.PHONY: all clean flash

all: $(PROJECT).elf $(PROJECT).bin $(PROJECT).hex $(PROJECT).lst
	$(SIZE) $(PROJECT).elf

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/main.o: main.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/startup.o: $(TARGET_DIR)/c_bsp/startup.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/system_stm32f1xx.o: $(TARGET_DIR)/c_bsp/system_stm32f1xx.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(PROJECT).elf: $(OBJS)
	$(CC) $(CFLAGS) $(OBJS) $(LDFLAGS) -o $@

$(PROJECT).bin: $(PROJECT).elf
	$(OBJCOPY) -O binary $< $@

$(PROJECT).hex: $(PROJECT).elf
	$(OBJCOPY) -O ihex $< $@

$(PROJECT).lst: $(PROJECT).elf
	$(OBJDUMP) -d -S $< > $@

flash: $(PROJECT).elf
	$(OPENOCD_BIN) -s $(OPENOCD_SCRIPTS) -f $(OPENOCD_CFG) \
		-c "init; reset halt; flash write_image erase $(CURDIR)/$(PROJECT).elf; reset run; shutdown"

clean:
	rm -rf $(BUILD_DIR) $(PROJECT).elf $(PROJECT).bin $(PROJECT).hex $(PROJECT).lst $(PROJECT).map *.o *.d

-include $(DEPS)
