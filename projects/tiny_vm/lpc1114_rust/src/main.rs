#![no_std]
#![no_main]

use core::ptr;

use cortex_m::interrupt;
use cortex_m_rt::entry;
use lpc1114_common::pac::Peripherals;
use lpc1114_common::{clock, systick, tiny_vm, uart};
use panic_halt as _;

const LED_PIN_BIT: u32 = 1 << 0; // PIO1_0
const TINY_VM_ACTIVITY_LED: bool = true;

const VM_UPLOAD_MAGIC0: u8 = b'T';
const VM_UPLOAD_MAGIC1: u8 = b'V';
const VM_UPLOAD_MAGIC2: u8 = b'M';
const VM_UPLOAD_MAGIC3: u8 = b'1';

const BOOT_UPLOAD_WINDOW_MS: u32 = 15_000;
const BYTE_TIMEOUT_MS: u32 = 250;
const WAIT_FOREVER_MS: u32 = u32::MAX;

const HOST_LED_WRITE: u8 = 0;
const HOST_DELAY_MS: u8 = 1;
const HOST_UART_PRINTLN_U32: u8 = 2;
const HOST_UART_PRINTLN_HEX32: u8 = 3;

fn host_delay_ms(ms: u32) {
    let start = systick::millis();
    while systick::millis().wrapping_sub(start) < ms {}
}

fn uart_read_byte_timeout(timeout_ms: u32) -> Option<u8> {
    let p = unsafe { Peripherals::steal() };
    let start = systick::millis();
    loop {
        if (p.UART.lsr.read().bits() & (1 << 0)) != 0 {
            return Some(p.UART.rbr().read().bits() as u8);
        }
        if timeout_ms != WAIT_FOREVER_MS && systick::millis().wrapping_sub(start) >= timeout_ms {
            return None;
        }
    }
}

fn wait_magic_start(timeout_ms: u32) -> bool {
    let start = systick::millis();
    loop {
        if timeout_ms != WAIT_FOREVER_MS && systick::millis().wrapping_sub(start) >= timeout_ms {
            return false;
        }
        if let Some(b) = uart_read_byte_timeout(1) {
            if b == VM_UPLOAD_MAGIC0 {
                return true;
            }
        }
    }
}

fn vm_receive_program(vm: &mut tiny_vm::TinyVm, first_byte_timeout_ms: u32) -> i32 {
    if !wait_magic_start(first_byte_timeout_ms) {
        return 0;
    }
    if uart_read_byte_timeout(BYTE_TIMEOUT_MS) != Some(VM_UPLOAD_MAGIC1) {
        return -1;
    }
    if uart_read_byte_timeout(BYTE_TIMEOUT_MS) != Some(VM_UPLOAD_MAGIC2) {
        return -1;
    }
    if uart_read_byte_timeout(BYTE_TIMEOUT_MS) != Some(VM_UPLOAD_MAGIC3) {
        return -1;
    }
    let lo = match uart_read_byte_timeout(BYTE_TIMEOUT_MS) {
        Some(v) => v as u16,
        None => return -1,
    };
    let hi = match uart_read_byte_timeout(BYTE_TIMEOUT_MS) {
        Some(v) => v as u16,
        None => return -1,
    };
    let len = (hi << 8) | lo;
    if len == 0 || len as usize > tiny_vm::TINY_VM_CODE_MAX {
        return -1;
    }

    let mut checksum = 0u8;
    let mut i = 0usize;
    while i < len as usize {
        let b = match uart_read_byte_timeout(BYTE_TIMEOUT_MS) {
            Some(v) => v,
            None => return -1,
        };
        vm.code[i] = b;
        checksum = checksum.wrapping_add(b);
        i += 1;
    }
    let expected = match uart_read_byte_timeout(BYTE_TIMEOUT_MS) {
        Some(v) => v,
        None => return -1,
    };
    if checksum != expected {
        return -1;
    }
    vm.code_len = len;
    vm.pc = 0;
    vm.sp = 0;
    vm.locals.fill(0);
    vm.mem.fill(0);
    tiny_vm::TINY_VM_OK
}

fn led_init() {
    let p = unsafe { Peripherals::steal() };
    unsafe {
        let mut ahb = p.SYSCON.sysahbclkctrl.read().bits();
        ahb |= (1 << 6) | (1 << 16);
        p.SYSCON.sysahbclkctrl.write(|w| w.bits(ahb));

        let mut v = p.IOCON.iocon_r_pio1_0.read().bits();
        v &= !0x7;
        v &= !((0x3 << 3) | (1 << 10));
        p.IOCON.iocon_r_pio1_0.write(|w| w.bits(v));

        p.GPIO1.dir.write(|w| w.bits(p.GPIO1.dir.read().bits() | LED_PIN_BIT));
        p.GPIO1.data.write(|w| w.bits(p.GPIO1.data.read().bits() & !LED_PIN_BIT));
    }
}

fn led_write(on: bool) {
    let p = unsafe { Peripherals::steal() };
    let mut next = p.GPIO1.data.read().bits();
    if on {
        next |= LED_PIN_BIT;
    } else {
        next &= !LED_PIN_BIT;
    }
    unsafe { p.GPIO1.data.write(|w| w.bits(next)) };
}

fn led_toggle() {
    let p = unsafe { Peripherals::steal() };
    let next = p.GPIO1.data.read().bits() ^ LED_PIN_BIT;
    unsafe { p.GPIO1.data.write(|w| w.bits(next)) };
}

fn vm_host_call(vm: &mut tiny_vm::TinyVm, id: u8, _ctx: *mut ()) -> i32 {
    match id {
        HOST_LED_WRITE => {
            let v = match vm.pop() {
                Ok(v) => v,
                Err(rc) => return rc,
            };
            led_write(v != 0);
            0
        }
        HOST_DELAY_MS => {
            let v = match vm.pop() {
                Ok(v) => v,
                Err(rc) => return rc,
            };
            let delay = if v < 0 { 0 } else { v as u32 };
            host_delay_ms(delay);
            0
        }
        HOST_UART_PRINTLN_U32 => {
            let v = match vm.pop() {
                Ok(v) => v,
                Err(rc) => return rc,
            };
            if v < 0 {
                uart::putc(b'-');
                uart::put_dec_u32(v.wrapping_neg() as u32);
            } else {
                uart::put_dec_u32(v as u32);
            }
            uart::puts("\r\n");
            0
        }
        HOST_UART_PRINTLN_HEX32 => {
            let uv = match vm.pop() {
                Ok(v) => v as u32,
                Err(rc) => return rc,
            };
            uart::put_hex8(((uv >> 24) & 0xFF) as u8);
            uart::put_hex8(((uv >> 16) & 0xFF) as u8);
            uart::put_hex8(((uv >> 8) & 0xFF) as u8);
            uart::put_hex8((uv & 0xFF) as u8);
            uart::puts("\r\n");
            0
        }
        _ => -1,
    }
}

fn vm_trace_led_hook(_vm: &mut tiny_vm::TinyVm, _op: u8, _ctx: *mut ()) {
    led_toggle();
}

#[entry]
fn main() -> ! {
    clock::init_48mhz();
    systick::init_1ms();
    uart::init_57600();
    unsafe { interrupt::enable() };
    led_init();

    let mut vm = tiny_vm::TinyVm::new(vm_host_call, ptr::null_mut());
    if TINY_VM_ACTIVITY_LED {
        vm.set_trace_hook(vm_trace_led_hook, ptr::null_mut());
    }

    uart::puts("tiny_vm: upload frame TVM1+len+code+sum\r\n");
    uart::puts("tiny_vm: boot window 15s\r\n");

    let mut rc = vm_receive_program(&mut vm, BOOT_UPLOAD_WINDOW_MS);
    if rc < 0 {
        uart::puts("tiny_vm: boot upload failed\r\n");
    } else {
        uart::puts("tiny_vm: image loaded\r\n");
    }

    loop {
        if vm.code_len == 0 {
            rc = vm_receive_program(&mut vm, WAIT_FOREVER_MS);
            if rc > 0 {
                uart::puts("tiny_vm: image loaded\r\n");
            } else {
                uart::puts("tiny_vm: upload failed\r\n");
                continue;
            }
        }

        rc = vm.exec(128);
        if rc == tiny_vm::TINY_VM_STEP_LIMIT {
            continue;
        }
        if rc == tiny_vm::TINY_VM_HALT {
            uart::puts("tiny_vm: halt\r\n");
        } else if rc < 0 {
            uart::puts("tiny_vm: runtime error\r\n");
        }
        vm.code_len = 0;
    }
}
