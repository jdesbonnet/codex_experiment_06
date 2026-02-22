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

Both runtimes wait 5 seconds after boot for an upload, then continue waiting for frames.

## Host tools

- assembler: `tools/vm_asm.py`
- minimal C-like compiler: `tools/vm_cc.py`
- uploader: `tools/vm_upload.py`
- host regression tests: `tools/test_vm_tools.py`

## Quick start

Compile sample source:
```sh
./tools/vm_cc.py projects/tiny_vm/count10.cvm.c -o /tmp/count10.bin
```

Flash tiny_vm runtime (LPC1114):
```sh
./tools/flash.sh --target lpc1114 --lang c --project tiny_vm
```

Upload bytecode to LPC1114 primary UART:
```sh
./tools/vm_upload.py /tmp/count10.bin --port /dev/ttyACM1 --baud 57600
```

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
- `+`, `-`, `<`, `>`, `==`
