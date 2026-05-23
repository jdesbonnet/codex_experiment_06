//! WebAssembly tiny_vm simulator.
//!
//! Bit-for-bit equivalent to `tools/dev_env/sim/tiny_vm_sim.py`, which is itself
//! a port of `common/src/tiny_vm.c`. The C runtime is the spec; any divergence
//! is a sim bug. See `common/include/tiny_vm.h` for the canonical constants,
//! opcode IDs, and status codes.
//!
//! Two faces:
//! - **Native API** (`TinyVm` struct, the bulk of this file). Used by
//!   `cargo test` and any non-wasm consumer.
//! - **wasm-bindgen wrapper** (`WasmTinyVm`, at the bottom, only compiled for
//!   `wasm32`). The browser-side DAP server in
//!   `tools/dev_env_web/extension/` talks to this.

// ---- constants — must match common/include/tiny_vm.h ----------------------

pub const TINY_VM_STACK_MAX: usize = 16;
pub const TINY_VM_CODE_MAX: usize = 512;
pub const TINY_VM_LOCALS_MAX: usize = 16;
pub const TINY_VM_MEM_MAX: usize = 128;

// Status codes — positive are termination states the C runtime defines plus
// HOST_PENDING which is unique to this in-browser sim (coroutine handshake
// between wasm and JS). Negative are errors mirroring tiny_vm_status_t.
pub const STATUS_OK: i32 = 0;
pub const STATUS_HALT: i32 = 1;
pub const STATUS_STEP_LIMIT: i32 = 2;
pub const STATUS_HOST_PENDING: i32 = 3;
pub const STATUS_ERR_PC_OOB: i32 = -1;
pub const STATUS_ERR_STACK_OVERFLOW: i32 = -2;
pub const STATUS_ERR_STACK_UNDERFLOW: i32 = -3;
pub const STATUS_ERR_BAD_OPCODE: i32 = -4;
pub const STATUS_ERR_HOST: i32 = -5;
pub const STATUS_ERR_CODE_TOO_LARGE: i32 = -6;
pub const STATUS_ERR_MEM_OOB: i32 = -7;

// Opcodes — must match tiny_vm_opcode_t in common/include/tiny_vm.h.
pub const OP_NOP: u8 = 0x00;
pub const OP_PUSH8: u8 = 0x01;
pub const OP_ADD: u8 = 0x02;
pub const OP_SUB: u8 = 0x03;
pub const OP_DUP: u8 = 0x04;
pub const OP_DROP: u8 = 0x05;
pub const OP_SWAP: u8 = 0x06;
pub const OP_JMP: u8 = 0x07;
pub const OP_JZ: u8 = 0x08;
pub const OP_HOST: u8 = 0x09;
pub const OP_LGET: u8 = 0x0A;
pub const OP_LSET: u8 = 0x0B;
pub const OP_EQ: u8 = 0x0C;
pub const OP_LT: u8 = 0x0D;
pub const OP_PUSH16: u8 = 0x0E;
pub const OP_MOD: u8 = 0x0F;
pub const OP_MUL: u8 = 0x10;
pub const OP_DIV: u8 = 0x11;
pub const OP_MGET: u8 = 0x12;
pub const OP_MSET: u8 = 0x13;
pub const OP_PUSH32: u8 = 0x14;
pub const OP_AND: u8 = 0x15;
pub const OP_OR: u8 = 0x16;
pub const OP_XOR: u8 = 0x17;
pub const OP_NOT: u8 = 0x18;
pub const OP_SHL: u8 = 0x19;
pub const OP_SHR: u8 = 0x1A;
pub const OP_ROL: u8 = 0x1B;
pub const OP_ROR: u8 = 0x1C;
pub const OP_MGET32: u8 = 0x1D;
pub const OP_MSET32: u8 = 0x1E;
pub const OP_HALT: u8 = 0xFF;

// ---- core VM --------------------------------------------------------------

/// Outcome of a single `step()`.
#[derive(Debug, Clone, Copy)]
pub struct StepResult {
    pub status: i32,
    pub op: u8,
    pub pc_before: u16,
    pub pc_after: u16,
}

/// Pure-Rust VM core. No wasm-bindgen here so it is fully usable from native
/// tests.
pub struct TinyVm {
    code: [u8; TINY_VM_CODE_MAX],
    code_len: u16,
    pc: u16,
    stack: [i32; TINY_VM_STACK_MAX],
    sp: u8,
    locals: [i32; TINY_VM_LOCALS_MAX],
    mem: [u8; TINY_VM_MEM_MAX],
    halted: bool,
    last_status: i32,
    /// Set to `Some(host_id)` after executing OP_HOST. JS-side completes the
    /// call (popping args, pushing result) and clears this via
    /// `complete_host_call(rc)`. Until then the VM is suspended.
    pending_host_call: Option<u8>,
}

impl TinyVm {
    pub fn new(bytecode: &[u8]) -> Result<Self, i32> {
        if bytecode.len() > TINY_VM_CODE_MAX {
            return Err(STATUS_ERR_CODE_TOO_LARGE);
        }
        let mut code = [0u8; TINY_VM_CODE_MAX];
        code[..bytecode.len()].copy_from_slice(bytecode);
        Ok(Self {
            code,
            code_len: bytecode.len() as u16,
            pc: 0,
            stack: [0; TINY_VM_STACK_MAX],
            sp: 0,
            locals: [0; TINY_VM_LOCALS_MAX],
            mem: [0; TINY_VM_MEM_MAX],
            halted: false,
            last_status: STATUS_OK,
            pending_host_call: None,
        })
    }

    // -- accessors used by the wasm wrapper, JS DAP, and native tests -------

    pub fn pc(&self) -> u16 { self.pc }
    pub fn sp(&self) -> u8 { self.sp }
    pub fn halted(&self) -> bool { self.halted }
    pub fn last_status(&self) -> i32 { self.last_status }
    pub fn code_len(&self) -> u16 { self.code_len }
    pub fn code_byte(&self, idx: u16) -> u8 {
        if (idx as usize) < self.code.len() { self.code[idx as usize] } else { 0 }
    }
    pub fn stack_at(&self, idx: u8) -> i32 {
        if idx < self.sp { self.stack[idx as usize] } else { 0 }
    }
    pub fn local_at(&self, idx: u8) -> i32 {
        if (idx as usize) < self.locals.len() { self.locals[idx as usize] } else { 0 }
    }
    pub fn set_local(&mut self, idx: u8, v: i32) {
        if (idx as usize) < self.locals.len() {
            self.locals[idx as usize] = v;
        }
    }
    pub fn mem_byte(&self, idx: u16) -> u8 {
        if (idx as usize) < self.mem.len() { self.mem[idx as usize] } else { 0 }
    }
    pub fn pending_host_id(&self) -> i32 {
        match self.pending_host_call {
            Some(id) => id as i32,
            None => -1,
        }
    }

    // -- stack primitives, exposed for host-call completion from JS ---------

    pub fn push(&mut self, v: i32) -> Result<(), i32> {
        if (self.sp as usize) >= TINY_VM_STACK_MAX {
            return Err(STATUS_ERR_STACK_OVERFLOW);
        }
        self.stack[self.sp as usize] = v;
        self.sp += 1;
        Ok(())
    }

    pub fn pop(&mut self) -> Result<i32, i32> {
        if self.sp == 0 {
            return Err(STATUS_ERR_STACK_UNDERFLOW);
        }
        self.sp -= 1;
        Ok(self.stack[self.sp as usize])
    }

    // -- byte reader (pc-bounded) --------------------------------------------

    fn read_u8(&mut self) -> Result<u8, i32> {
        if self.pc >= self.code_len {
            return Err(STATUS_ERR_PC_OOB);
        }
        let v = self.code[self.pc as usize];
        self.pc += 1;
        Ok(v)
    }

    fn read_u16_le(&mut self) -> Result<u16, i32> {
        let lo = self.read_u8()? as u16;
        let hi = self.read_u8()? as u16;
        Ok((hi << 8) | lo)
    }

    fn read_i16_le(&mut self) -> Result<i16, i32> {
        Ok(self.read_u16_le()? as i16)
    }

    fn read_i32_le(&mut self) -> Result<i32, i32> {
        let b0 = self.read_u8()? as u32;
        let b1 = self.read_u8()? as u32;
        let b2 = self.read_u8()? as u32;
        let b3 = self.read_u8()? as u32;
        Ok((b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)) as i32)
    }

    // -- execution -----------------------------------------------------------

    /// Complete a pending host call. If `rc < 0` the VM halts with ERR_HOST.
    pub fn complete_host_call(&mut self, rc: i32) {
        self.pending_host_call = None;
        if rc < 0 {
            self.halted = true;
            self.last_status = STATUS_ERR_HOST;
        }
    }

    /// Execute exactly one bytecode instruction. If the instruction is
    /// OP_HOST, the host_id byte is consumed and `pending_host_id()` returns
    /// it; the caller must then complete the host call via
    /// `complete_host_call(rc)` before the next `step()`.
    pub fn step(&mut self) -> StepResult {
        if self.halted {
            return StepResult {
                status: self.last_status,
                op: 0,
                pc_before: self.pc,
                pc_after: self.pc,
            };
        }
        if self.pending_host_call.is_some() {
            return StepResult {
                status: STATUS_HOST_PENDING,
                op: OP_HOST,
                pc_before: self.pc,
                pc_after: self.pc,
            };
        }
        let pc_before = self.pc;
        let op = match self.read_u8() {
            Ok(v) => v,
            Err(status) => {
                self.halted = true;
                self.last_status = status;
                return StepResult {
                    status,
                    op: 0,
                    pc_before,
                    pc_after: self.pc,
                };
            }
        };
        let status = match self.execute(op) {
            Ok(()) => {
                if self.pending_host_call.is_some() {
                    STATUS_HOST_PENDING
                } else {
                    STATUS_OK
                }
            }
            Err(STATUS_HALT) => {
                self.halted = true;
                self.last_status = STATUS_HALT;
                STATUS_HALT
            }
            Err(s) => {
                self.halted = true;
                self.last_status = s;
                s
            }
        };
        StepResult {
            status,
            op,
            pc_before,
            pc_after: self.pc,
        }
    }

    /// Run until HALT, an error, a step-budget exhaustion, or a pending host
    /// call. Returns the final status.
    pub fn run(&mut self, step_budget: u32) -> i32 {
        let mut steps: u32 = 0;
        while steps < step_budget && !self.halted && self.pending_host_call.is_none() {
            let res = self.step();
            steps += 1;
            if res.status != STATUS_OK {
                return res.status;
            }
        }
        if self.halted {
            return self.last_status;
        }
        if self.pending_host_call.is_some() {
            return STATUS_HOST_PENDING;
        }
        STATUS_STEP_LIMIT
    }

    fn execute(&mut self, op: u8) -> Result<(), i32> {
        match op {
            OP_NOP => Ok(()),
            OP_PUSH8 => {
                let v = self.read_u8()? as i8 as i32;
                self.push(v)
            }
            OP_PUSH16 => {
                let v = self.read_i16_le()? as i32;
                self.push(v)
            }
            OP_PUSH32 => {
                let v = self.read_i32_le()?;
                self.push(v)
            }
            OP_ADD => {
                let b = self.pop()?;
                let a = self.pop()?;
                self.push(a.wrapping_add(b))
            }
            OP_SUB => {
                let b = self.pop()?;
                let a = self.pop()?;
                self.push(a.wrapping_sub(b))
            }
            OP_DUP => {
                if self.sp == 0 {
                    return Err(STATUS_ERR_STACK_UNDERFLOW);
                }
                let top = self.stack[(self.sp - 1) as usize];
                self.push(top)
            }
            OP_DROP => {
                self.pop()?;
                Ok(())
            }
            OP_SWAP => {
                if self.sp < 2 {
                    return Err(STATUS_ERR_STACK_UNDERFLOW);
                }
                let top = self.sp as usize - 1;
                self.stack.swap(top, top - 1);
                Ok(())
            }
            OP_JMP => {
                let target = self.read_u16_le()?;
                if target >= self.code_len {
                    return Err(STATUS_ERR_PC_OOB);
                }
                self.pc = target;
                Ok(())
            }
            OP_JZ => {
                let target = self.read_u16_le()?;
                let cond = self.pop()?;
                if cond == 0 {
                    if target >= self.code_len {
                        return Err(STATUS_ERR_PC_OOB);
                    }
                    self.pc = target;
                }
                Ok(())
            }
            OP_HOST => {
                let host_id = self.read_u8()?;
                self.pending_host_call = Some(host_id);
                Ok(())
            }
            OP_LGET => {
                let slot = self.read_u8()?;
                if (slot as usize) >= TINY_VM_LOCALS_MAX {
                    return Err(STATUS_ERR_BAD_OPCODE);
                }
                self.push(self.locals[slot as usize])
            }
            OP_LSET => {
                let slot = self.read_u8()?;
                if (slot as usize) >= TINY_VM_LOCALS_MAX {
                    return Err(STATUS_ERR_BAD_OPCODE);
                }
                let v = self.pop()?;
                self.locals[slot as usize] = v;
                Ok(())
            }
            OP_EQ => {
                let b = self.pop()?;
                let a = self.pop()?;
                self.push(if a == b { 1 } else { 0 })
            }
            OP_LT => {
                let b = self.pop()?;
                let a = self.pop()?;
                self.push(if a < b { 1 } else { 0 })
            }
            OP_MOD => {
                let b = self.pop()?;
                let a = self.pop()?;
                if b == 0 {
                    return Err(STATUS_ERR_HOST);
                }
                // Rust i32 % truncates toward zero — same as C.
                self.push(a.wrapping_rem(b))
            }
            OP_MUL => {
                let b = self.pop()?;
                let a = self.pop()?;
                self.push(a.wrapping_mul(b))
            }
            OP_DIV => {
                let b = self.pop()?;
                let a = self.pop()?;
                if b == 0 {
                    return Err(STATUS_ERR_HOST);
                }
                // i32::MIN / -1 wraps in wrapping_div — same as C UB but defined.
                self.push(a.wrapping_div(b))
            }
            OP_MGET => {
                let idx = self.pop()?;
                if idx < 0 || (idx as usize) >= TINY_VM_MEM_MAX {
                    return Err(STATUS_ERR_MEM_OOB);
                }
                self.push(self.mem[idx as usize] as i32)
            }
            OP_MSET => {
                let value = self.pop()?;
                let idx = self.pop()?;
                if idx < 0 || (idx as usize) >= TINY_VM_MEM_MAX {
                    return Err(STATUS_ERR_MEM_OOB);
                }
                self.mem[idx as usize] = (value & 0xFF) as u8;
                Ok(())
            }
            OP_MGET32 => {
                let idx = self.pop()?;
                if idx < 0 || (idx as usize) > TINY_VM_MEM_MAX - 4 {
                    return Err(STATUS_ERR_MEM_OOB);
                }
                let i = idx as usize;
                let v = (self.mem[i] as u32)
                    | ((self.mem[i + 1] as u32) << 8)
                    | ((self.mem[i + 2] as u32) << 16)
                    | ((self.mem[i + 3] as u32) << 24);
                self.push(v as i32)
            }
            OP_MSET32 => {
                let value = self.pop()?;
                let idx = self.pop()?;
                if idx < 0 || (idx as usize) > TINY_VM_MEM_MAX - 4 {
                    return Err(STATUS_ERR_MEM_OOB);
                }
                let i = idx as usize;
                let u = value as u32;
                self.mem[i] = (u & 0xFF) as u8;
                self.mem[i + 1] = ((u >> 8) & 0xFF) as u8;
                self.mem[i + 2] = ((u >> 16) & 0xFF) as u8;
                self.mem[i + 3] = ((u >> 24) & 0xFF) as u8;
                Ok(())
            }
            OP_AND => {
                let b = self.pop()?;
                let a = self.pop()?;
                self.push(((a as u32) & (b as u32)) as i32)
            }
            OP_OR => {
                let b = self.pop()?;
                let a = self.pop()?;
                self.push(((a as u32) | (b as u32)) as i32)
            }
            OP_XOR => {
                let b = self.pop()?;
                let a = self.pop()?;
                self.push(((a as u32) ^ (b as u32)) as i32)
            }
            OP_NOT => {
                let a = self.pop()?;
                self.push((!(a as u32)) as i32)
            }
            OP_SHL => {
                let b = self.pop()?;
                let a = self.pop()?;
                let shift = (b as u32) & 31;
                self.push(((a as u32).wrapping_shl(shift)) as i32)
            }
            OP_SHR => {
                let b = self.pop()?;
                let a = self.pop()?;
                let shift = (b as u32) & 31;
                self.push(((a as u32).wrapping_shr(shift)) as i32)
            }
            OP_ROL => {
                let b = self.pop()?;
                let a = self.pop()?;
                let shift = (b as u32) & 31;
                self.push((a as u32).rotate_left(shift) as i32)
            }
            OP_ROR => {
                let b = self.pop()?;
                let a = self.pop()?;
                let shift = (b as u32) & 31;
                self.push((a as u32).rotate_right(shift) as i32)
            }
            OP_HALT => Err(STATUS_HALT),
            _ => Err(STATUS_ERR_BAD_OPCODE),
        }
    }
}

// ---- wasm-bindgen wrapper -------------------------------------------------

#[cfg(target_arch = "wasm32")]
mod wasm {
    use super::*;
    use wasm_bindgen::prelude::*;

    /// JS-facing handle. Wraps `TinyVm` and exposes the methods the in-browser
    /// DAP server (`tools/dev_env_web/extension/src/browser/debugAdapter.ts`)
    /// needs. Methods that can fail return `i32` status codes — JS reads them
    /// and translates to DAP events.
    #[wasm_bindgen]
    pub struct WasmTinyVm {
        inner: TinyVm,
    }

    #[wasm_bindgen]
    pub struct WasmStepResult {
        pub status: i32,
        pub op: u8,
        pub pc_before: u16,
        pub pc_after: u16,
    }

    #[wasm_bindgen]
    impl WasmTinyVm {
        #[wasm_bindgen(constructor)]
        pub fn new(code: &[u8]) -> Result<WasmTinyVm, JsValue> {
            TinyVm::new(code)
                .map(|inner| WasmTinyVm { inner })
                .map_err(|status| JsValue::from(status))
        }

        pub fn step(&mut self) -> WasmStepResult {
            let r = self.inner.step();
            WasmStepResult {
                status: r.status,
                op: r.op,
                pc_before: r.pc_before,
                pc_after: r.pc_after,
            }
        }

        pub fn run(&mut self, step_budget: u32) -> i32 {
            self.inner.run(step_budget)
        }

        pub fn pc(&self) -> u16 { self.inner.pc() }
        pub fn sp(&self) -> u8 { self.inner.sp() }
        pub fn halted(&self) -> bool { self.inner.halted() }
        pub fn last_status(&self) -> i32 { self.inner.last_status() }
        pub fn code_len(&self) -> u16 { self.inner.code_len() }
        pub fn code_byte(&self, idx: u16) -> u8 { self.inner.code_byte(idx) }
        pub fn stack_at(&self, idx: u8) -> i32 { self.inner.stack_at(idx) }
        pub fn local_at(&self, idx: u8) -> i32 { self.inner.local_at(idx) }
        pub fn set_local(&mut self, idx: u8, v: i32) { self.inner.set_local(idx, v) }
        pub fn mem_byte(&self, idx: u16) -> u8 { self.inner.mem_byte(idx) }
        pub fn pending_host_id(&self) -> i32 { self.inner.pending_host_id() }

        pub fn push(&mut self, v: i32) -> i32 {
            match self.inner.push(v) {
                Ok(()) => STATUS_OK,
                Err(s) => s,
            }
        }
        pub fn pop(&mut self) -> i32 {
            // Wasm interop convention: return the value, or STATUS_ERR_STACK_UNDERFLOW
            // on empty. Callers should check pending_host_id() and sp() before
            // popping, just like the C runtime.
            self.inner.pop().unwrap_or(STATUS_ERR_STACK_UNDERFLOW)
        }
        pub fn complete_host_call(&mut self, rc: i32) {
            self.inner.complete_host_call(rc)
        }
    }
}

// ---- native tests ---------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Run with a default host that records output, matching DefaultHostCalls
    /// in tools/dev_env/sim/host_calls.py.
    fn run_with_default_host(code: &[u8]) -> (i32, Vec<String>) {
        let mut vm = TinyVm::new(code).expect("bytecode under CODE_MAX");
        let mut stdout: Vec<String> = Vec::new();
        loop {
            let status = vm.run(1_000_000);
            if status == STATUS_HOST_PENDING {
                let host_id = vm.pending_host_id() as u8;
                let rc = handle_host(&mut vm, host_id, &mut stdout);
                vm.complete_host_call(rc);
                continue;
            }
            return (status, stdout);
        }
    }

    fn handle_host(vm: &mut TinyVm, host_id: u8, stdout: &mut Vec<String>) -> i32 {
        match host_id {
            0 => {
                // LED_WRITE: pop one arg, no effect on stdout.
                if vm.pop().is_err() { return -1; }
                0
            }
            1 => {
                // DELAY_MS: pop one arg, no effect (sim does not actually delay).
                if vm.pop().is_err() { return -1; }
                0
            }
            2 => {
                // UART_PRINTLN_U32: pop signed decimal, push "<n>\n".
                let v = match vm.pop() { Ok(v) => v, Err(_) => return -1 };
                stdout.push(format!("{}\n", v));
                0
            }
            3 => {
                // UART_PRINTLN_HEX32: pop, push "<XXXXXXXX>\n".
                let v = match vm.pop() { Ok(v) => v, Err(_) => return -1 };
                stdout.push(format!("{:08X}\n", v as u32));
                0
            }
            _ => -1,
        }
    }

    #[test]
    fn nop_then_halt() {
        let (status, out) = run_with_default_host(&[OP_NOP, OP_HALT]);
        assert_eq!(status, STATUS_HALT);
        assert!(out.is_empty());
    }

    #[test]
    fn push8_print_u32() {
        // PUSH8 42; HOST 2; HALT
        let (status, out) = run_with_default_host(&[OP_PUSH8, 42, OP_HOST, 2, OP_HALT]);
        assert_eq!(status, STATUS_HALT);
        assert_eq!(out, vec!["42\n".to_string()]);
    }

    #[test]
    fn push8_sign_extended() {
        // PUSH8 0xFF (= -1); HOST 2; HALT
        let (status, out) = run_with_default_host(&[OP_PUSH8, 0xFF, OP_HOST, 2, OP_HALT]);
        assert_eq!(status, STATUS_HALT);
        assert_eq!(out, vec!["-1\n".to_string()]);
    }

    #[test]
    fn add_sub_mul_div_mod() {
        // 7 + 3 = 10
        let (s, o) = run_with_default_host(&[
            OP_PUSH8, 7, OP_PUSH8, 3, OP_ADD, OP_HOST, 2, OP_HALT,
        ]);
        assert_eq!(s, STATUS_HALT);
        assert_eq!(o, vec!["10\n".to_string()]);

        // 7 - 10 = -3
        let (s, o) = run_with_default_host(&[
            OP_PUSH8, 7, OP_PUSH8, 10, OP_SUB, OP_HOST, 2, OP_HALT,
        ]);
        assert_eq!(s, STATUS_HALT);
        assert_eq!(o, vec!["-3\n".to_string()]);

        // 6 * 7 = 42
        let (s, o) = run_with_default_host(&[
            OP_PUSH8, 6, OP_PUSH8, 7, OP_MUL, OP_HOST, 2, OP_HALT,
        ]);
        assert_eq!(s, STATUS_HALT);
        assert_eq!(o, vec!["42\n".to_string()]);

        // -7 / 2 = -3 (C truncates toward zero)
        let (s, o) = run_with_default_host(&[
            OP_PUSH8, (-7i8) as u8, OP_PUSH8, 2, OP_DIV, OP_HOST, 2, OP_HALT,
        ]);
        assert_eq!(s, STATUS_HALT);
        assert_eq!(o, vec!["-3\n".to_string()]);

        // -7 % 2 = -1 (sign of dividend)
        let (s, o) = run_with_default_host(&[
            OP_PUSH8, (-7i8) as u8, OP_PUSH8, 2, OP_MOD, OP_HOST, 2, OP_HALT,
        ]);
        assert_eq!(s, STATUS_HALT);
        assert_eq!(o, vec!["-1\n".to_string()]);
    }

    #[test]
    fn div_by_zero_errors() {
        let (status, _) = run_with_default_host(&[OP_PUSH8, 1, OP_PUSH8, 0, OP_DIV, OP_HALT]);
        assert_eq!(status, STATUS_ERR_HOST);
    }

    #[test]
    fn count10_loop() {
        // Hand-assembled count10:
        //   PUSH8 1     ; i = 1
        //   LSET 0
        // loop:
        //   LGET 0
        //   PUSH8 11
        //   LT
        //   JZ end
        //   LGET 0
        //   HOST 2      ; print i
        //   LGET 0
        //   PUSH8 1
        //   ADD
        //   LSET 0
        //   JMP loop
        // end:
        //   HALT
        let mut code: Vec<u8> = vec![];
        code.extend_from_slice(&[OP_PUSH8, 1, OP_LSET, 0]);
        let loop_pc = code.len();
        code.extend_from_slice(&[OP_LGET, 0, OP_PUSH8, 11, OP_LT]);
        // JZ end-placeholder
        code.push(OP_JZ);
        let jz_imm = code.len();
        code.extend_from_slice(&[0, 0]);
        code.extend_from_slice(&[OP_LGET, 0, OP_HOST, 2]);
        code.extend_from_slice(&[OP_LGET, 0, OP_PUSH8, 1, OP_ADD, OP_LSET, 0]);
        code.push(OP_JMP);
        let loop_pc_le = (loop_pc as u16).to_le_bytes();
        code.extend_from_slice(&loop_pc_le);
        let end_pc = code.len() as u16;
        code.push(OP_HALT);
        // Patch JZ target.
        code[jz_imm..jz_imm + 2].copy_from_slice(&end_pc.to_le_bytes());

        let (status, out) = run_with_default_host(&code);
        assert_eq!(status, STATUS_HALT);
        let expected: Vec<String> = (1..=10).map(|i| format!("{}\n", i)).collect();
        assert_eq!(out, expected);
    }

    #[test]
    fn stack_overflow_caught() {
        // 17 pushes — STACK_MAX = 16
        let mut code: Vec<u8> = vec![];
        for _ in 0..17 {
            code.push(OP_PUSH8);
            code.push(1);
        }
        code.push(OP_HALT);
        let (status, _) = run_with_default_host(&code);
        assert_eq!(status, STATUS_ERR_STACK_OVERFLOW);
    }

    #[test]
    fn mem_round_trip_32() {
        // PUSH 4 (idx), PUSH 0xDEADBEEF, MSET32, PUSH 4, MGET32, HOST 3, HALT
        let mut code: Vec<u8> = vec![];
        code.extend_from_slice(&[OP_PUSH8, 4]);
        // 0xDEADBEEF as i32
        code.push(OP_PUSH32);
        code.extend_from_slice(&0xDEADBEEFu32.to_le_bytes());
        code.push(OP_MSET32);
        code.extend_from_slice(&[OP_PUSH8, 4, OP_MGET32, OP_HOST, 3, OP_HALT]);
        let (status, out) = run_with_default_host(&code);
        assert_eq!(status, STATUS_HALT);
        assert_eq!(out, vec!["DEADBEEF\n".to_string()]);
    }

    #[test]
    fn bit_ops() {
        // (0x000000F0 OR 0x0000000F) AND 0x000000FF = 0xFF.
        // Use PUSH32 to load explicit 32-bit values; PUSH8 sign-extends and
        // would turn 0xF0 into 0xFFFFFFF0, which is not what we want to test
        // here.
        let mut code: Vec<u8> = vec![];
        code.push(OP_PUSH32);
        code.extend_from_slice(&0x000000F0u32.to_le_bytes());
        code.push(OP_PUSH32);
        code.extend_from_slice(&0x0000000Fu32.to_le_bytes());
        code.push(OP_OR);
        code.push(OP_PUSH32);
        code.extend_from_slice(&0x000000FFu32.to_le_bytes());
        code.push(OP_AND);
        code.extend_from_slice(&[OP_HOST, 3, OP_HALT]);
        let (status, out) = run_with_default_host(&code);
        assert_eq!(status, STATUS_HALT);
        assert_eq!(out, vec!["000000FF\n".to_string()]);
    }

    #[test]
    fn rotate_left() {
        // rotate_left(0x12345678, 8) = 0x34567812
        let mut code: Vec<u8> = vec![];
        code.push(OP_PUSH32);
        code.extend_from_slice(&0x12345678u32.to_le_bytes());
        code.extend_from_slice(&[OP_PUSH8, 8, OP_ROL, OP_HOST, 3, OP_HALT]);
        let (status, out) = run_with_default_host(&code);
        assert_eq!(status, STATUS_HALT);
        assert_eq!(out, vec!["34567812\n".to_string()]);
    }

    #[test]
    fn bad_opcode_errors() {
        // 0x7F is unassigned in the opcode space.
        let (status, _) = run_with_default_host(&[0x7F, OP_HALT]);
        assert_eq!(status, STATUS_ERR_BAD_OPCODE);
    }
}
