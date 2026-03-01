#![no_std]

use ch32v0::ch32v003::Peripherals;
use lpc1114_common::tiny_vm::{self, TinyVm};
use panic_halt as _;

const LED_PIN_SHIFT: u32 = 4;
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

#[no_mangle]
pub extern "C" fn rust_tiny_vm_main() -> ! {
    uart_init_57600_rx_tx();
    led_init();

    let mut vm = TinyVm::new(vm_host_call, core::ptr::null_mut());
    if TINY_VM_ACTIVITY_LED {
        vm.set_trace_hook(vm_trace_led_hook, core::ptr::null_mut());
    }

    uart_puts("tiny_vm: upload frame TVM1+len+code+sum\r\n");
    uart_puts("tiny_vm: boot window 15s\r\n");

    let mut rc = vm_receive_program(&mut vm, BOOT_UPLOAD_WINDOW_MS);
    if rc < 0 {
        uart_puts("tiny_vm: boot upload failed\r\n");
    } else {
        uart_puts("tiny_vm: image loaded\r\n");
    }

    loop {
        if vm.code_len == 0 {
            rc = vm_receive_program(&mut vm, WAIT_FOREVER_MS);
            if rc > 0 {
                uart_puts("tiny_vm: image loaded\r\n");
            } else {
                uart_puts("tiny_vm: upload failed\r\n");
                continue;
            }
        }

        rc = vm.exec(128);
        if rc == tiny_vm::TINY_VM_STEP_LIMIT {
            continue;
        }
        if rc == tiny_vm::TINY_VM_HALT {
            uart_puts("tiny_vm: halt\r\n");
        } else if rc < 0 {
            uart_puts("tiny_vm: runtime error\r\n");
        }
        vm.code_len = 0;
    }
}

fn uart_init_57600_rx_tx() {
    let p = unsafe { Peripherals::steal() };
    let brr = ((48_000_000u32 + 28_800u32) / 57_600u32) as u16;

    p.RCC
        .apb2pcenr()
        .modify(|_, w| w.iopden().set_bit().usart1en().set_bit());

    p.GPIOD.cfglr().modify(|r, w| unsafe {
        let mut bits = r.bits();
        bits &= !(0xFu32 << (4 * 5));
        bits |= 0xBu32 << (4 * 5);
        bits &= !(0xFu32 << (4 * 6));
        bits |= 0x4u32 << (4 * 6);
        w.bits(bits)
    });

    p.USART1.ctlr1().write(|w| {
        w.m().clear_bit();
        w.pce().clear_bit();
        w.te().set_bit();
        w.re().set_bit();
        w
    });
    p.USART1.ctlr2().reset();
    p.USART1.ctlr3().reset();
    p.USART1.brr().write(|w| unsafe { w.bits(u32::from(brr)) });
    p.USART1.ctlr1().modify(|_, w| w.ue().set_bit());
}

fn uart_read_byte_timeout(timeout_ms: u32) -> Option<u8> {
    let p = unsafe { Peripherals::steal() };
    let mut remain = timeout_ms;
    loop {
        if p.USART1.statr().read().rxne().bit_is_set() {
            return Some((p.USART1.datar().read().bits() & 0xFF) as u8);
        }
        if timeout_ms != WAIT_FOREVER_MS {
            if remain == 0 {
                return None;
            }
            remain = remain.wrapping_sub(1);
            delay_ms(1);
        }
    }
}

fn wait_magic_start(timeout_ms: u32) -> bool {
    let mut remain = timeout_ms;
    loop {
        if timeout_ms != WAIT_FOREVER_MS {
            if remain == 0 {
                return false;
            }
            remain = remain.wrapping_sub(1);
        }
        if let Some(b) = uart_read_byte_timeout(1) {
            if b == VM_UPLOAD_MAGIC0 {
                return true;
            }
        }
    }
}

fn vm_receive_program(vm: &mut TinyVm, first_byte_timeout_ms: u32) -> i32 {
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

fn vm_host_call(vm: &mut TinyVm, id: u8, _ctx: *mut ()) -> i32 {
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
            delay_ms(if v < 0 { 0 } else { v as u32 });
            0
        }
        HOST_UART_PRINTLN_U32 => {
            let v = match vm.pop() {
                Ok(v) => v,
                Err(rc) => return rc,
            };
            if v < 0 {
                uart_putc(b'-');
                uart_put_dec_u32(v.wrapping_neg() as u32);
            } else {
                uart_put_dec_u32(v as u32);
            }
            uart_puts("\r\n");
            0
        }
        HOST_UART_PRINTLN_HEX32 => {
            let uv = match vm.pop() {
                Ok(v) => v as u32,
                Err(rc) => return rc,
            };
            uart_put_hex8(((uv >> 24) & 0xFF) as u8);
            uart_put_hex8(((uv >> 16) & 0xFF) as u8);
            uart_put_hex8(((uv >> 8) & 0xFF) as u8);
            uart_put_hex8((uv & 0xFF) as u8);
            uart_puts("\r\n");
            0
        }
        _ => -1,
    }
}

fn vm_trace_led_hook(_vm: &mut TinyVm, _op: u8, _ctx: *mut ()) {
    led_toggle();
}

fn led_init() {
    let p = unsafe { Peripherals::steal() };
    p.RCC.apb2pcenr().modify(|_, w| w.iopden().set_bit());
    p.GPIOD.cfglr().modify(|r, w| unsafe {
        let bits = (r.bits() & !(0xFu32 << (4 * LED_PIN_SHIFT))) | (0x1u32 << (4 * LED_PIN_SHIFT));
        w.bits(bits)
    });
    led_write(false);
}

fn led_write(on: bool) {
    let p = unsafe { Peripherals::steal() };
    if on {
        p.GPIOD.bshr().write(|w| w.bs4().set_bit());
    } else {
        p.GPIOD.bshr().write(|w| w.br4().set_bit());
    }
}

fn led_toggle() {
    let p = unsafe { Peripherals::steal() };
    let is_on = p.GPIOD.outdr().read().odr4().bit_is_set();
    if is_on {
        p.GPIOD.bshr().write(|w| w.bs4().set_bit());
    } else {
        p.GPIOD.bshr().write(|w| w.br4().set_bit());
    }
}

fn uart_putc(c: u8) {
    let p = unsafe { Peripherals::steal() };
    while p.USART1.statr().read().txe().bit_is_clear() {}
    p.USART1.datar().write(|w| unsafe { w.bits(c as u32) });
}

fn uart_puts(s: &str) {
    for b in s.as_bytes() {
        uart_putc(*b);
    }
}

fn uart_put_hex8(v: u8) {
    const HEX: &[u8; 16] = b"0123456789ABCDEF";
    uart_putc(HEX[(v >> 4) as usize]);
    uart_putc(HEX[(v & 0x0F) as usize]);
}

fn uart_put_dec_u32(mut v: u32) {
    let mut buf = [0u8; 10];
    if v == 0 {
        uart_putc(b'0');
        return;
    }
    let mut i = 0usize;
    while v > 0 && i < buf.len() {
        buf[i] = b'0' + (v % 10) as u8;
        v /= 10;
        i += 1;
    }
    while i > 0 {
        i -= 1;
        uart_putc(buf[i]);
    }
}

fn delay_ms(ms: u32) {
    let mut outer = 0u32;
    while outer < ms {
        let mut inner = 0u32;
        while inner < 8_000 {
            unsafe { core::arch::asm!("nop") };
            inner = inner.wrapping_add(1);
        }
        outer = outer.wrapping_add(1);
    }
}
