TOP := blink
PROJECT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
BUILD_DIR := $(PROJECT_DIR)build
PART := xc3s500e-vq100-4
UCF := $(PROJECT_DIR)papilio_one_wa4.ucf
BIT := $(BUILD_DIR)/$(TOP).bit

.PHONY: all clean load check-toolchain

all: $(BIT)

check-toolchain:
	@for tool in xst ngdbuild map par bitgen; do \
		command -v $$tool >/dev/null 2>&1 || { \
			echo "missing: $$tool (Xilinx ISE command-line tool)"; \
			exit 1; \
		}; \
	done

$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/$(TOP).prj: $(PROJECT_DIR)$(TOP).v | $(BUILD_DIR)
	@printf "verilog work %s\n" "$(PROJECT_DIR)$(TOP).v" > $@

$(BUILD_DIR)/$(TOP).xst: | $(BUILD_DIR)
	@{ \
		echo "run"; \
		echo "-ifn $(BUILD_DIR)/$(TOP).prj"; \
		echo "-ifmt mixed"; \
		echo "-ofn $(BUILD_DIR)/$(TOP).ngc"; \
		echo "-top $(TOP)"; \
		echo "-p $(PART)"; \
	} > $@

$(BUILD_DIR)/$(TOP).ngc: $(PROJECT_DIR)$(TOP).v $(BUILD_DIR)/$(TOP).prj $(BUILD_DIR)/$(TOP).xst check-toolchain
	@xst -ifn $(BUILD_DIR)/$(TOP).xst

$(BUILD_DIR)/$(TOP).ngd: $(BUILD_DIR)/$(TOP).ngc $(UCF) check-toolchain
	@ngdbuild -p $(PART) -uc $(UCF) -dd $(BUILD_DIR) $(BUILD_DIR)/$(TOP).ngc $@

$(BUILD_DIR)/$(TOP)_map.ncd: $(BUILD_DIR)/$(TOP).ngd check-toolchain
	@map -p $(PART) -o $@ $(BUILD_DIR)/$(TOP).ngd

$(BUILD_DIR)/$(TOP).ncd: $(BUILD_DIR)/$(TOP)_map.ncd check-toolchain
	@par -w $(BUILD_DIR)/$(TOP)_map.ncd $@

$(BIT): $(BUILD_DIR)/$(TOP).ncd check-toolchain
	@bitgen -w $(BUILD_DIR)/$(TOP).ncd $@

load: $(BIT)
	@openocd -s /usr/share/openocd/scripts \
		-f $(PROJECT_DIR)../../../targets/papilio_one/openocd/base.cfg \
		-c "init; pld load 0 $(BIT); shutdown"

clean:
	@rm -rf $(BUILD_DIR)
