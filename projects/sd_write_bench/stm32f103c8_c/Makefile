PROJECT := sd_write_bench
REPO_ROOT := ../../..
TARGET_DIR := $(REPO_ROOT)/targets/stm32f103c8
BUILD_DIR := build

CC := arm-none-eabi-gcc
OBJCOPY := arm-none-eabi-objcopy
OBJDUMP := arm-none-eabi-objdump
SIZE := arm-none-eabi-size
SD_SPI_BENCH_DIV ?= 8
SD_WRITE_BENCH_BYTES ?= 65536
STM32_BENCH_SYSCLK_HZ ?= 8000000

CFLAGS := -mcpu=cortex-m3 -mthumb -Og -g -ffunction-sections -fdata-sections
CFLAGS += -fno-unwind-tables -fno-asynchronous-unwind-tables
CFLAGS += -Wall -Wextra -Werror -Wshadow -std=c11
CFLAGS += -DSTM32F103xB
CFLAGS += -DSD_SPI_BENCH_DIV=$(SD_SPI_BENCH_DIV)
CFLAGS += -DSD_WRITE_BENCH_BYTES=$(SD_WRITE_BENCH_BYTES)
CFLAGS += -DSTM32_BENCH_SYSCLK_HZ=$(STM32_BENCH_SYSCLK_HZ)
CFLAGS += -I$(TARGET_DIR)/c_bsp/include -I$(CURDIR)/fatfs
CFLAGS += -MMD -MP

LDFLAGS := -T $(TARGET_DIR)/linker/stm32f103c8.ld -nostartfiles
LDFLAGS += -Wl,--gc-sections -Wl,-Map,$(PROJECT).map

OBJS := \
	$(BUILD_DIR)/main.o \
	$(BUILD_DIR)/ff.o \
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

$(BUILD_DIR)/ff.o: fatfs/ff.c | $(BUILD_DIR)
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
