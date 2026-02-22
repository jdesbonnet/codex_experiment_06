# tiny_vm (planned)

Goal: a very small interpreted bytecode VM that can run on both LPC1114 and CH32V003.

Initial targets:
- `projects/tiny_vm/lpc1114_c`
- `projects/tiny_vm/ch32v003_c`

Planned v1 architecture:
- stack-based bytecode VM (data stack + return stack + program counter)
- fixed-size buffers only (no dynamic allocation)
- strict bounds checks (stack/code/opcode validation)
- hardware calls via target HAL wrappers

Planned v1 opcode groups:
- stack: `PUSH`, `DROP`, `DUP`, `SWAP`, `OVER`
- ALU: `ADD`, `SUB`, `AND`, `OR`, `XOR`, `SHL`, `SHR`, `EQ`, `LT`, `GT`
- control flow: `JMP`, `JZ`, `JNZ`, `CALL`, `RET`, `HALT`
- device: `DELAY_MS`, `PIN_MODE`, `PIN_WRITE`, `PIN_READ`, `UART_PUTC`, `SLEEP_MS`

Host-side plan:
- small assembler (`tools/vm_asm.py`) to convert text mnemonics to bytecode
- optional bytecode loader over UART
