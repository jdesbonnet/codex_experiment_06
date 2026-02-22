#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;
use lpc1114_common::{systick, uart};
use lpc1114_common::pac::Peripherals;
use cortex_m::interrupt;

#[entry]
fn main() -> ! {
    let p = unsafe { Peripherals::steal() };

    // Enable GPIO + IOCON clocks (IOCON needed for UART pins).
    unsafe {
        let mut ahb = p.SYSCON.sysahbclkctrl.read().bits();
        ahb |= (1 << 6) | (1 << 16);
        p.SYSCON.sysahbclkctrl.write(|w| w.bits(ahb));
    }

    // Stay on default 12 MHz IRC for now.
    systick::init_1ms_12mhz();
    uart::init_57600();
    unsafe { interrupt::enable(); }

    let mut counter: u32 = 0;
    loop {
        uart::puts("Rust test ");
        uart::put_dec_u32(counter);
        uart::puts("\r\n");
        counter = counter.wrapping_add(1);
        delay_ms(1000);
    }
}

fn delay_ms(ms: u32) {
    let start = systick::millis();
    while systick::millis().wrapping_sub(start) < ms {}
}
