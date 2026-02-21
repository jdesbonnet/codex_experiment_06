#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;
use lpc1114_common::{clock, systick, uart};
use lpc1114_common::pac::Peripherals;

#[entry]
fn main() -> ! {
    let p = unsafe { Peripherals::steal() };
    unsafe {
        let mut ahb = p.SYSCON.sysahbclkctrl.read().bits();
        ahb |= (1 << 6) | (1 << 16);
        p.SYSCON.sysahbclkctrl.write(|w| w.bits(ahb));
    }

    clock::init_48mhz();
    systick::init_1ms();
    uart::init_57600();

    uart::puts("UART smoke test\r\n");

    loop {
        cortex_m::asm::wfi();
    }
}
