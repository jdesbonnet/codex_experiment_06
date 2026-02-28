# tiny_vm

Small stack-based bytecode VM running on both:
- `projects/tiny_vm/lpc1114_c`
- `projects/tiny_vm/ch32v003_c`

## Runtime protocol

Targets now execute uploaded bytecode (no built-in hardcoded program).

Upload frame format:
- magic: `TVM1` (4 bytes)
- length: little-endian `uint16`
- payload: bytecode
- checksum: `sum(payload) & 0xff`

Both runtimes wait 15 seconds after boot for an upload, then continue waiting for frames.

## Host tools

- assembler: `tools/vm_asm.py`
- minimal C-like compiler: `tools/vm_cc.py`
- uploader: `tools/vm_upload.py`
- host regression tests: `tools/test_vm_tools.py`
- hardware UART regression tests: `tools/test_tiny_vm_hardware.py`

## Quick start

Compile sample source:
```sh
./tools/vm_cc.py projects/tiny_vm/count10.cvm.c -o /tmp/count10.bin
```

Compile prime-number demo (up to 1000):
```sh
./tools/vm_cc.py projects/tiny_vm/primes1000.cvm.c -o /tmp/primes1000.bin
```

Flash tiny_vm runtime (LPC1114):
```sh
./tools/flash.sh --target lpc1114 --lang c --project tiny_vm
```

Upload bytecode to LPC1114 primary UART:
```sh
./tools/vm_upload.py /tmp/count10.bin --port /dev/ttyACM1 --baud 57600
```

Prime demo upload:
```sh
./tools/vm_upload.py /tmp/primes1000.bin --port /dev/ttyACM1 --baud 57600
```

Compile Collatz max-step demo (range 1..100):
```sh
./tools/vm_cc.py projects/tiny_vm/collatz_max.cvm.c -o /tmp/collatz_max.bin
./tools/vm_upload.py /tmp/collatz_max.bin --port /dev/ttyACM1 --baud 57600
```

Expected output:
```text
97
118
```

## Hardware Regression

Run all finite-output LPC1114 demo regressions:
```sh
python3 tools/test_tiny_vm_hardware.py
```

Run one case only:
```sh
python3 tools/test_tiny_vm_hardware.py --only collatz_max
```

Notes:
- the script auto-detects debugprobe primary/mirror UART ports
- it reflashes the LPC1114 `tiny_vm` runtime by default
- it verifies exact UART output for:
  - `count10`
  - `primes1000`
  - `collatz_max`
- `blink.cvm.c` is intentionally excluded because it does not emit UART output and does not halt

## C-like language subset (v1)

- declarations:
- `const int NAME = <const_expr>;`
- `int var;`
- `int var = <expr>;`
- statements:
- assignment: `var = <expr>;`
- `while (<expr>) { ... }`
- `if (<expr>) { ... } else { ... }`
- calls:
- `led_write(expr);`
- `delay_ms(expr);`
- `print_u32(expr);`
- `host(const_expr, expr);`
- expressions:
- literals, vars, consts
- `+`, `-`, `*`, `/`, `%`, `<`, `>`, `==`

Assembler/VM opcodes now include:
- `PUSH8`, `PUSH16`
- arithmetic/comparison: `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, `EQ`, `LT`
- locals: `LGET`, `LSET`
