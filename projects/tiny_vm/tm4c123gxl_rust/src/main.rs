#![no_std]
#![no_main]

use core::ptr::{read_volatile, write_volatile};
use core::sync::atomic::{AtomicU32, Ordering};

use cortex_m::peripheral::syst::SystClkSource;
use cortex_m_rt::{entry, exception};
use panic_halt as _;

#[path = "../../../../common/rust/src/tiny_vm.rs"]
mod tiny_vm;

const LED_PIN_BIT: u32 = 1 << 1; // PF1, LaunchPad red LED
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

const SYSCTL_RCGCUART: usize = 0x400F_E618;
const SYSCTL_RCGCGPIO: usize = 0x400F_E608;
const SYSCTL_PRUART: usize = 0x400F_EA18;
const SYSCTL_PRGPIO: usize = 0x400F_EA08;

const GPIO_PORTA_DIR: usize = 0x4000_4400;
const GPIO_PORTA_AFSEL: usize = 0x4000_4420;
const GPIO_PORTA_DR2R: usize = 0x4000_4500;
const GPIO_PORTA_DEN: usize = 0x4000_451C;
const GPIO_PORTA_AMSEL: usize = 0x4000_4528;
const GPIO_PORTA_PCTL: usize = 0x4000_452C;

const GPIO_PORTF_DATA: usize = 0x4002_53FC;
const GPIO_PORTF_DIR: usize = 0x4002_5400;
const GPIO_PORTF_AFSEL: usize = 0x4002_5420;
const GPIO_PORTF_DR2R: usize = 0x4002_5500;
const GPIO_PORTF_DEN: usize = 0x4002_551C;
const GPIO_PORTF_LOCK: usize = 0x4002_5520;
const GPIO_PORTF_CR: usize = 0x4002_5524;
const GPIO_PORTF_AMSEL: usize = 0x4002_5528;
const GPIO_PORTF_PCTL: usize = 0x4002_552C;

const UART0_DR: usize = 0x4000_C000;
const UART0_FR: usize = 0x4000_C018;
const UART0_IBRD: usize = 0x4000_C024;
const UART0_FBRD: usize = 0x4000_C028;
const UART0_LCRH: usize = 0x4000_C02C;
const UART0_CTL: usize = 0x4000_C030;
const UART0_CC: usize = 0x4000_CFC8;

const UART_FR_RXFE: u32 = 1 << 4;
const UART_FR_TXFF: u32 = 1 << 5;

const UART_LCRH_FEN: u32 = 1 << 4;
const UART_LCRH_WLEN_8: u32 = 3 << 5;

const UART_CTL_UARTEN: u32 = 1 << 0;
const UART_CTL_TXE: u32 = 1 << 8;
const UART_CTL_RXE: u32 = 1 << 9;

const UART_CC_CS_PIOSC: u32 = 0x5;

const UART_BAUD_115200_IBRD: u32 = 8;
const UART_BAUD_115200_FBRD: u32 = 44;

static MS_TICKS: AtomicU32 = AtomicU32::new(0);

#[exception]
fn SysTick() {
    MS_TICKS.fetch_add(1, Ordering::Relaxed);
}

#[inline]
fn read_reg(addr: usize) -> u32 {
    unsafe { read_volatile(addr as *const u32) }
}

#[inline]
fn write_reg(addr: usize, value: u32) {
    unsafe { write_volatile(addr as *mut u32, value) };
}

#[inline]
fn modify_reg(addr: usize, f: impl FnOnce(u32) -> u32) {
    let value = read_reg(addr);
    write_reg(addr, f(value));
}

fn millis() -> u32 {
    MS_TICKS.load(Ordering::Relaxed)
}

fn delay_ms(delay_ms: u32) {
    let start = millis();
    while millis().wrapping_sub(start) < delay_ms {}
}

fn systick_init_1ms() {
    let mut p = cortex_m::Peripherals::take().unwrap();
    let syst = &mut p.SYST;
    syst.set_clock_source(SystClkSource::Core);
    syst.set_reload(16_000 - 1);
    syst.clear_current();
    syst.enable_interrupt();
    syst.enable_counter();
}

fn uart0_init_115200() {
    modify_reg(SYSCTL_RCGCGPIO, |v| v | (1 << 0));
    modify_reg(SYSCTL_RCGCUART, |v| v | (1 << 0));

    while (read_reg(SYSCTL_PRGPIO) & (1 << 0)) == 0 {}
    while (read_reg(SYSCTL_PRUART) & (1 << 0)) == 0 {}

    modify_reg(UART0_CTL, |v| v & !(UART_CTL_UARTEN | UART_CTL_TXE | UART_CTL_RXE));
    write_reg(UART0_CC, UART_CC_CS_PIOSC);
    write_reg(UART0_IBRD, UART_BAUD_115200_IBRD);
    write_reg(UART0_FBRD, UART_BAUD_115200_FBRD);
    write_reg(UART0_LCRH, UART_LCRH_WLEN_8 | UART_LCRH_FEN);

    modify_reg(GPIO_PORTA_AMSEL, |v| v & !0x3);
    modify_reg(GPIO_PORTA_PCTL, |v| (v & !0xFF) | 0x11);
    modify_reg(GPIO_PORTA_AFSEL, |v| v | 0x3);
    modify_reg(GPIO_PORTA_DEN, |v| v | 0x3);
    modify_reg(GPIO_PORTA_DR2R, |v| v | (1 << 1));
    modify_reg(GPIO_PORTA_DIR, |v| (v & !(1 << 0)) | (1 << 1));

    write_reg(UART0_CTL, UART_CTL_UARTEN | UART_CTL_TXE | UART_CTL_RXE);
}

fn uart0_putc(ch: u8) {
    while (read_reg(UART0_FR) & UART_FR_TXFF) != 0 {}
    write_reg(UART0_DR, ch as u32);
}

fn uart0_puts(text: &str) {
    for ch in text.bytes() {
        uart0_putc(ch);
    }
}

fn uart0_put_hex8(value: u8) {
    const HEX: &[u8; 16] = b"0123456789ABCDEF";
    uart0_putc(HEX[((value >> 4) & 0x0F) as usize]);
    uart0_putc(HEX[(value & 0x0F) as usize]);
}

fn uart0_put_dec_u32(mut value: u32) {
    let mut buffer = [0u8; 10];
    let mut i = 0usize;

    if value == 0 {
        uart0_putc(b'0');
        return;
    }

    while value != 0 {
        buffer[i] = b'0' + (value % 10) as u8;
        value /= 10;
        i += 1;
    }

    while i != 0 {
        i -= 1;
        uart0_putc(buffer[i]);
    }
}

fn uart_read_byte_timeout(timeout_ms: u32) -> Option<u8> {
    let start = millis();
    loop {
        if (read_reg(UART0_FR) & UART_FR_RXFE) == 0 {
            return Some((read_reg(UART0_DR) & 0xFF) as u8);
        }
        if timeout_ms != WAIT_FOREVER_MS && millis().wrapping_sub(start) >= timeout_ms {
            return None;
        }
    }
}

fn wait_magic_start(timeout_ms: u32) -> bool {
    let start = millis();
    loop {
        if timeout_ms != WAIT_FOREVER_MS && millis().wrapping_sub(start) >= timeout_ms {
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
    modify_reg(SYSCTL_RCGCGPIO, |v| v | (1 << 5));
    while (read_reg(SYSCTL_PRGPIO) & (1 << 5)) == 0 {}

    write_reg(GPIO_PORTF_LOCK, 0x4C4F434B);
    modify_reg(GPIO_PORTF_CR, |v| v | LED_PIN_BIT);
    modify_reg(GPIO_PORTF_AMSEL, |v| v & !LED_PIN_BIT);
    modify_reg(GPIO_PORTF_PCTL, |v| v & !(0xF << 4));
    modify_reg(GPIO_PORTF_AFSEL, |v| v & !LED_PIN_BIT);
    modify_reg(GPIO_PORTF_DIR, |v| v | LED_PIN_BIT);
    modify_reg(GPIO_PORTF_DR2R, |v| v | LED_PIN_BIT);
    modify_reg(GPIO_PORTF_DEN, |v| v | LED_PIN_BIT);
    modify_reg(GPIO_PORTF_DATA, |v| v & !LED_PIN_BIT);
}

fn led_write(on: bool) {
    modify_reg(GPIO_PORTF_DATA, |v| if on { v | LED_PIN_BIT } else { v & !LED_PIN_BIT });
}

fn led_toggle() {
    modify_reg(GPIO_PORTF_DATA, |v| v ^ LED_PIN_BIT);
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
            delay_ms(if v < 0 { 0 } else { v as u32 });
            0
        }
        HOST_UART_PRINTLN_U32 => {
            let v = match vm.pop() {
                Ok(v) => v,
                Err(rc) => return rc,
            };
            if v < 0 {
                uart0_putc(b'-');
                uart0_put_dec_u32(v.wrapping_neg() as u32);
            } else {
                uart0_put_dec_u32(v as u32);
            }
            uart0_puts("\r\n");
            0
        }
        HOST_UART_PRINTLN_HEX32 => {
            let uv = match vm.pop() {
                Ok(v) => v as u32,
                Err(rc) => return rc,
            };
            uart0_put_hex8(((uv >> 24) & 0xFF) as u8);
            uart0_put_hex8(((uv >> 16) & 0xFF) as u8);
            uart0_put_hex8(((uv >> 8) & 0xFF) as u8);
            uart0_put_hex8((uv & 0xFF) as u8);
            uart0_puts("\r\n");
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
    systick_init_1ms();
    uart0_init_115200();
    led_init();

    let mut vm = tiny_vm::TinyVm::new(vm_host_call, core::ptr::null_mut());
    if TINY_VM_ACTIVITY_LED {
        vm.set_trace_hook(vm_trace_led_hook, core::ptr::null_mut());
    }

    uart0_puts("tiny_vm: upload frame TVM1+len+code+sum\r\n");
    uart0_puts("tiny_vm: boot window 15s\r\n");

    let mut rc = vm_receive_program(&mut vm, BOOT_UPLOAD_WINDOW_MS);
    if rc < 0 {
        uart0_puts("tiny_vm: boot upload failed\r\n");
    } else {
        uart0_puts("tiny_vm: image loaded\r\n");
    }

    loop {
        if vm.code_len == 0 {
            rc = vm_receive_program(&mut vm, WAIT_FOREVER_MS);
            if rc > 0 {
                uart0_puts("tiny_vm: image loaded\r\n");
            } else {
                uart0_puts("tiny_vm: upload failed\r\n");
                continue;
            }
        }

        rc = vm.exec(128);
        if rc == tiny_vm::TINY_VM_STEP_LIMIT {
            continue;
        }
        if rc == tiny_vm::TINY_VM_HALT {
            uart0_puts("tiny_vm: halt\r\n");
        } else if rc < 0 {
            uart0_puts("tiny_vm: runtime error\r\n");
        }
        vm.code_len = 0;
    }
}
