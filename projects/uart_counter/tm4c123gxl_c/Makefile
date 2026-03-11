PROJECT := uart_counter
REPO_ROOT := ../../..
TARGET_DIR := $(REPO_ROOT)/targets/tm4c123gxl
BUILD_DIR := build

CC := arm-none-eabi-gcc
OBJCOPY := arm-none-eabi-objcopy
OBJDUMP := arm-none-eabi-objdump
SIZE := arm-none-eabi-size

CFLAGS := -mcpu=cortex-m4 -mthumb -Og -g -ffunction-sections -fdata-sections
CFLAGS += -Wall -Wextra -Werror -Wshadow -std=c11
CFLAGS += -I$(TARGET_DIR)/c_bsp/include
CFLAGS += -MMD -MP

LDFLAGS := -T $(TARGET_DIR)/linker/tm4c123gh6pm.ld -nostartfiles
LDFLAGS += -Wl,--gc-sections -Wl,-Map,$(PROJECT).map

OBJS := \
	$(BUILD_DIR)/main.o \
	$(BUILD_DIR)/startup.o

DEPS := $(OBJS:.o=.d)

OPENOCD_BIN ?= openocd
OPENOCD_SCRIPTS ?= /usr/share/openocd/scripts
OPENOCD_PROJECT_SCRIPTS ?= $(REPO_ROOT)/openocd
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

$(PROJECT).elf: $(OBJS)
	$(CC) $(CFLAGS) $(OBJS) $(LDFLAGS) -o $@

$(PROJECT).bin: $(PROJECT).elf
	$(OBJCOPY) -O binary $< $@

$(PROJECT).hex: $(PROJECT).elf
	$(OBJCOPY) -O ihex $< $@

$(PROJECT).lst: $(PROJECT).elf
	$(OBJDUMP) -d -S $< > $@

flash: $(PROJECT).elf
	$(OPENOCD_BIN) -s $(OPENOCD_SCRIPTS) -s $(OPENOCD_PROJECT_SCRIPTS) -f $(OPENOCD_CFG) \
		-c "init; reset halt; flash write_image erase $(CURDIR)/$(PROJECT).elf; reset run; shutdown"

clean:
	rm -rf $(BUILD_DIR) $(PROJECT).elf $(PROJECT).bin $(PROJECT).hex $(PROJECT).lst $(PROJECT).map *.o *.d

-include $(DEPS)
