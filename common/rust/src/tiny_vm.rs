#![allow(dead_code)]

pub const TINY_VM_OK: i32 = 0;
pub const TINY_VM_HALT: i32 = 1;
pub const TINY_VM_STEP_LIMIT: i32 = 2;
pub const TINY_VM_ERR_PC_OOB: i32 = -1;
pub const TINY_VM_ERR_STACK_OVERFLOW: i32 = -2;
pub const TINY_VM_ERR_STACK_UNDERFLOW: i32 = -3;
pub const TINY_VM_ERR_BAD_OPCODE: i32 = -4;
pub const TINY_VM_ERR_HOST: i32 = -5;
pub const TINY_VM_ERR_CODE_TOO_LARGE: i32 = -6;
pub const TINY_VM_ERR_MEM_OOB: i32 = -7;

pub const TINY_OP_NOP: u8 = 0x00;
pub const TINY_OP_PUSH8: u8 = 0x01;
pub const TINY_OP_ADD: u8 = 0x02;
pub const TINY_OP_SUB: u8 = 0x03;
pub const TINY_OP_DUP: u8 = 0x04;
pub const TINY_OP_DROP: u8 = 0x05;
pub const TINY_OP_SWAP: u8 = 0x06;
pub const TINY_OP_JMP: u8 = 0x07;
pub const TINY_OP_JZ: u8 = 0x08;
pub const TINY_OP_HOST: u8 = 0x09;
pub const TINY_OP_LGET: u8 = 0x0A;
pub const TINY_OP_LSET: u8 = 0x0B;
pub const TINY_OP_EQ: u8 = 0x0C;
pub const TINY_OP_LT: u8 = 0x0D;
pub const TINY_OP_PUSH16: u8 = 0x0E;
pub const TINY_OP_MOD: u8 = 0x0F;
pub const TINY_OP_MUL: u8 = 0x10;
pub const TINY_OP_DIV: u8 = 0x11;
pub const TINY_OP_MGET: u8 = 0x12;
pub const TINY_OP_MSET: u8 = 0x13;
pub const TINY_OP_PUSH32: u8 = 0x14;
pub const TINY_OP_AND: u8 = 0x15;
pub const TINY_OP_OR: u8 = 0x16;
pub const TINY_OP_XOR: u8 = 0x17;
pub const TINY_OP_NOT: u8 = 0x18;
pub const TINY_OP_SHL: u8 = 0x19;
pub const TINY_OP_SHR: u8 = 0x1A;
pub const TINY_OP_ROL: u8 = 0x1B;
pub const TINY_OP_ROR: u8 = 0x1C;
pub const TINY_OP_MGET32: u8 = 0x1D;
pub const TINY_OP_MSET32: u8 = 0x1E;
pub const TINY_OP_HALT: u8 = 0xFF;

pub const TINY_VM_STACK_MAX: usize = 16;
pub const TINY_VM_CODE_MAX: usize = 512;
pub const TINY_VM_LOCALS_MAX: usize = 16;
pub const TINY_VM_MEM_MAX: usize = 128;

pub type TinyVmHostCall = fn(&mut TinyVm, u8, *mut ()) -> i32;
pub type TinyVmTraceHook = fn(&mut TinyVm, u8, *mut ());

pub struct TinyVm {
    pub code: [u8; TINY_VM_CODE_MAX],
    pub code_len: u16,
    pub pc: u16,
    pub stack: [i32; TINY_VM_STACK_MAX],
    pub locals: [i32; TINY_VM_LOCALS_MAX],
    pub mem: [u8; TINY_VM_MEM_MAX],
    pub sp: u8,
    host_call: Option<TinyVmHostCall>,
    host_ctx: *mut (),
    trace_hook: Option<TinyVmTraceHook>,
    trace_ctx: *mut (),
}

impl TinyVm {
    pub fn new(host_call: TinyVmHostCall, host_ctx: *mut ()) -> Self {
        Self {
            code: [0; TINY_VM_CODE_MAX],
            code_len: 0,
            pc: 0,
            stack: [0; TINY_VM_STACK_MAX],
            locals: [0; TINY_VM_LOCALS_MAX],
            mem: [0; TINY_VM_MEM_MAX],
            sp: 0,
            host_call: Some(host_call),
            host_ctx,
            trace_hook: None,
            trace_ctx: core::ptr::null_mut(),
        }
    }

    pub fn set_trace_hook(&mut self, trace_hook: TinyVmTraceHook, trace_ctx: *mut ()) {
        self.trace_hook = Some(trace_hook);
        self.trace_ctx = trace_ctx;
    }

    pub fn clear_trace_hook(&mut self) {
        self.trace_hook = None;
        self.trace_ctx = core::ptr::null_mut();
    }

    pub fn load(&mut self, code: &[u8]) -> i32 {
        if code.len() > TINY_VM_CODE_MAX {
            return TINY_VM_ERR_CODE_TOO_LARGE;
        }
        self.code[..code.len()].copy_from_slice(code);
        self.code_len = code.len() as u16;
        self.pc = 0;
        self.sp = 0;
        self.locals.fill(0);
        self.mem.fill(0);
        TINY_VM_OK
    }

    pub fn push(&mut self, v: i32) -> i32 {
        if self.sp as usize >= TINY_VM_STACK_MAX {
            return TINY_VM_ERR_STACK_OVERFLOW;
        }
        self.stack[self.sp as usize] = v;
        self.sp = self.sp.wrapping_add(1);
        TINY_VM_OK
    }

    pub fn pop(&mut self) -> Result<i32, i32> {
        if self.sp == 0 {
            return Err(TINY_VM_ERR_STACK_UNDERFLOW);
        }
        self.sp = self.sp.wrapping_sub(1);
        Ok(self.stack[self.sp as usize])
    }

    fn read_u8(&mut self) -> Result<u8, i32> {
        if self.pc >= self.code_len {
            return Err(TINY_VM_ERR_PC_OOB);
        }
        let out = self.code[self.pc as usize];
        self.pc = self.pc.wrapping_add(1);
        Ok(out)
    }

    fn read_u16(&mut self) -> Result<u16, i32> {
        let lo = self.read_u8()? as u16;
        let hi = self.read_u8()? as u16;
        Ok((hi << 8) | lo)
    }

    fn read_i16(&mut self) -> Result<i32, i32> {
        Ok((self.read_u16()? as i16) as i32)
    }

    fn read_i32(&mut self) -> Result<i32, i32> {
        let b0 = self.read_u8()? as u32;
        let b1 = self.read_u8()? as u32;
        let b2 = self.read_u8()? as u32;
        let b3 = self.read_u8()? as u32;
        Ok(((b3 << 24) | (b2 << 16) | (b1 << 8) | b0) as i32)
    }

    pub fn exec(&mut self, step_budget: u32) -> i32 {
        let mut steps = 0u32;
        while steps < step_budget {
            let op = match self.read_u8() {
                Ok(v) => v,
                Err(rc) => return rc,
            };
            if let Some(trace_hook) = self.trace_hook {
                trace_hook(self, op, self.trace_ctx);
            }

            let rc = match op {
                TINY_OP_NOP => TINY_VM_OK,
                TINY_OP_PUSH8 => {
                    let v = match self.read_u8() {
                        Ok(v) => (v as i8) as i32,
                        Err(rc) => return rc,
                    };
                    self.push(v)
                }
                TINY_OP_PUSH16 => {
                    let v = match self.read_i16() {
                        Ok(v) => v,
                        Err(rc) => return rc,
                    };
                    self.push(v)
                }
                TINY_OP_PUSH32 => {
                    let v = match self.read_i32() {
                        Ok(v) => v,
                        Err(rc) => return rc,
                    };
                    self.push(v)
                }
                TINY_OP_ADD => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    self.push(a.wrapping_add(b))
                }
                TINY_OP_SUB => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    self.push(a.wrapping_sub(b))
                }
                TINY_OP_DUP => {
                    if self.sp == 0 {
                        TINY_VM_ERR_STACK_UNDERFLOW
                    } else {
                        self.push(self.stack[self.sp as usize - 1])
                    }
                }
                TINY_OP_DROP => match self.pop() {
                    Ok(_) => TINY_VM_OK,
                    Err(rc) => rc,
                },
                TINY_OP_SWAP => {
                    if self.sp < 2 {
                        TINY_VM_ERR_STACK_UNDERFLOW
                    } else {
                        let a = self.stack[self.sp as usize - 1];
                        self.stack[self.sp as usize - 1] = self.stack[self.sp as usize - 2];
                        self.stack[self.sp as usize - 2] = a;
                        TINY_VM_OK
                    }
                }
                TINY_OP_JMP => {
                    let target = match self.read_u16() { Ok(v) => v, Err(rc) => return rc };
                    if target >= self.code_len {
                        TINY_VM_ERR_PC_OOB
                    } else {
                        self.pc = target;
                        TINY_VM_OK
                    }
                }
                TINY_OP_JZ => {
                    let target = match self.read_u16() { Ok(v) => v, Err(rc) => return rc };
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    if a == 0 {
                        if target >= self.code_len {
                            TINY_VM_ERR_PC_OOB
                        } else {
                            self.pc = target;
                            TINY_VM_OK
                        }
                    } else {
                        TINY_VM_OK
                    }
                }
                TINY_OP_HOST => {
                    let host_id = match self.read_u8() { Ok(v) => v, Err(rc) => return rc };
                    if let Some(host_call) = self.host_call {
                        host_call(self, host_id, self.host_ctx)
                    } else {
                        TINY_VM_ERR_HOST
                    }
                }
                TINY_OP_LGET => {
                    let index = match self.read_u8() { Ok(v) => v as usize, Err(rc) => return rc };
                    if index >= TINY_VM_LOCALS_MAX {
                        TINY_VM_ERR_BAD_OPCODE
                    } else {
                        self.push(self.locals[index])
                    }
                }
                TINY_OP_LSET => {
                    let index = match self.read_u8() { Ok(v) => v as usize, Err(rc) => return rc };
                    if index >= TINY_VM_LOCALS_MAX {
                        TINY_VM_ERR_BAD_OPCODE
                    } else {
                        let v = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                        self.locals[index] = v;
                        TINY_VM_OK
                    }
                }
                TINY_OP_EQ => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    self.push(if a == b { 1 } else { 0 })
                }
                TINY_OP_LT => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    self.push(if a < b { 1 } else { 0 })
                }
                TINY_OP_MOD => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    if b == 0 { TINY_VM_ERR_HOST } else { self.push(a % b) }
                }
                TINY_OP_MUL => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    self.push(a.wrapping_mul(b))
                }
                TINY_OP_DIV => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    if b == 0 { TINY_VM_ERR_HOST } else { self.push(a / b) }
                }
                TINY_OP_MGET => {
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    if a < 0 || a as usize >= TINY_VM_MEM_MAX {
                        TINY_VM_ERR_MEM_OOB
                    } else {
                        self.push(self.mem[a as usize] as i32)
                    }
                }
                TINY_OP_MSET => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    if a < 0 || a as usize >= TINY_VM_MEM_MAX {
                        TINY_VM_ERR_MEM_OOB
                    } else {
                        self.mem[a as usize] = (b & 0xFF) as u8;
                        TINY_VM_OK
                    }
                }
                TINY_OP_MGET32 => {
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    if a < 0 || a as usize > TINY_VM_MEM_MAX - 4 {
                        TINY_VM_ERR_MEM_OOB
                    } else {
                        let i = a as usize;
                        let value = (self.mem[i] as u32)
                            | ((self.mem[i + 1] as u32) << 8)
                            | ((self.mem[i + 2] as u32) << 16)
                            | ((self.mem[i + 3] as u32) << 24);
                        self.push(value as i32)
                    }
                }
                TINY_OP_MSET32 => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc };
                    if a < 0 || a as usize > TINY_VM_MEM_MAX - 4 {
                        TINY_VM_ERR_MEM_OOB
                    } else {
                        let i = a as usize;
                        self.mem[i] = (b & 0xFF) as u8;
                        self.mem[i + 1] = ((b >> 8) & 0xFF) as u8;
                        self.mem[i + 2] = ((b >> 16) & 0xFF) as u8;
                        self.mem[i + 3] = ((b >> 24) & 0xFF) as u8;
                        TINY_VM_OK
                    }
                }
                TINY_OP_AND => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    self.push((a & b) as i32)
                }
                TINY_OP_OR => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    self.push((a | b) as i32)
                }
                TINY_OP_XOR => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    self.push((a ^ b) as i32)
                }
                TINY_OP_NOT => {
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    self.push((!a) as i32)
                }
                TINY_OP_SHL => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    self.push(a.wrapping_shl(b & 31) as i32)
                }
                TINY_OP_SHR => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    self.push(a.wrapping_shr(b & 31) as i32)
                }
                TINY_OP_ROL => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    self.push(a.rotate_left(b & 31) as i32)
                }
                TINY_OP_ROR => {
                    let b = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    let a = match self.pop() { Ok(v) => v, Err(rc) => return rc } as u32;
                    self.push(a.rotate_right(b & 31) as i32)
                }
                TINY_OP_HALT => return TINY_VM_HALT,
                _ => TINY_VM_ERR_BAD_OPCODE,
            };

            if rc < 0 {
                return rc;
            }
            steps = steps.wrapping_add(1);
        }
        TINY_VM_STEP_LIMIT
    }
}
