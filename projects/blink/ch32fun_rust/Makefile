TARGET := blink_rust
TARGET_MCU ?= CH32V003
TARGET_EXT := c

RUST_TARGET := riscv32e-unknown-none-elf
RUST_PROFILE := release
RUST_MANIFEST := ../rust_ch32v003/Cargo.toml
CARGO_TARGET_DIR := ../rust_ch32v003/target
RUST_LIB_DIR := $(CARGO_TARGET_DIR)/$(RUST_TARGET)/$(RUST_PROFILE)
RUST_LIB := $(RUST_LIB_DIR)/libblink_ch32v003_rust.a

EXTRA_ELF_DEPENDENCIES += $(RUST_LIB)
LDFLAGS += -L$(RUST_LIB_DIR) -lblink_ch32v003_rust

include ../../../third_party/ch32fun/ch32fun/ch32fun.mk

$(RUST_LIB):
	bash -lc 'source "$$HOME/.cargo/env" 2>/dev/null || true; rustup toolchain install nightly --profile minimal >/dev/null; rustup +nightly component add rust-src >/dev/null; CARGO_TARGET_DIR=$(CARGO_TARGET_DIR) cargo +nightly build -Z build-std=core --target $(RUST_TARGET) --$(RUST_PROFILE) --manifest-path $(RUST_MANIFEST)'

all: build
flash: cv_flash
clean: cv_clean
