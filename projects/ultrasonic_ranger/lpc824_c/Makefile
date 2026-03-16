PROJECT := ultrasonic_ranger
REPO_ROOT := ../../..
TARGET_DIR := $(REPO_ROOT)/targets/lpc824
FAMILY_DIR := $(REPO_ROOT)/targets/lpc8xx
BUILD_DIR := build

CC := arm-none-eabi-gcc
OBJCOPY := arm-none-eabi-objcopy
OBJDUMP := arm-none-eabi-objdump
SIZE := arm-none-eabi-size

CFLAGS := -mcpu=cortex-m0plus -mthumb -Og -g -ffunction-sections -fdata-sections
CFLAGS += -Wall -Wextra -Werror -Wshadow -std=c11
CFLAGS += -DCPU_LPC824M201JDH20 -D__START=main -D__STARTUP_CLEAR_BSS
CFLAGS += -I$(TARGET_DIR)/c_bsp/include
CFLAGS += -I$(FAMILY_DIR)/c_bsp/include
CFLAGS += -MMD -MP

LDFLAGS := -T $(TARGET_DIR)/linker/LPC824_flash.ld -nostartfiles
LDFLAGS += -Wl,--gc-sections -Wl,-Map,$(PROJECT).map
LDFLAGS += -Wl,--defsym=__heap_size__=0 -Wl,--defsym=__stack_size__=0x200

OBJS := \
	$(BUILD_DIR)/main.o \
	$(BUILD_DIR)/startup_LPC824.o \
	$(BUILD_DIR)/system_LPC824.o

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

$(BUILD_DIR)/startup_LPC824.o: $(TARGET_DIR)/c_bsp/startup_LPC824.S | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/system_LPC824.o: $(TARGET_DIR)/c_bsp/system_LPC824.c | $(BUILD_DIR)
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
		-c "init; reset halt; program $(CURDIR)/$(PROJECT).elf verify reset exit"

clean:
	rm -rf $(BUILD_DIR) $(PROJECT).elf $(PROJECT).bin $(PROJECT).hex $(PROJECT).lst $(PROJECT).map *.o *.d

-include $(DEPS)
