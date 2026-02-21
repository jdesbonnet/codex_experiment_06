#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;
use lpc1114_common::pac::Peripherals;
use cortex_m::asm;
use lpc1114_common::systick;

#[entry]
fn main() -> ! {
    let p = unsafe { Peripherals::steal() };

    // Enable GPIO + IOCON
    unsafe {
        let mut ahb = p.SYSCON.sysahbclkctrl.read().bits();
        ahb |= (1 << 6) | (1 << 16);
        p.SYSCON.sysahbclkctrl.write(|w| w.bits(ahb));
    }

    // Stay on default 12 MHz IRC.
    systick::init_1ms_12mhz();

    // PIO1_0 as GPIO (FUNC=1) push-pull.
    unsafe {
        p.IOCON.iocon_r_pio1_0.write(|w| w.bits((p.IOCON.iocon_r_pio1_0.read().bits() & !0x7) | 0x1));
        p.IOCON.iocon_r_pio1_0.write(|w| w.bits(p.IOCON.iocon_r_pio1_0.read().bits() & !(1 << 10)));
        p.GPIO1.dir.write(|w| w.bits(p.GPIO1.dir.read().bits() | (1 << 0)));
    }

    loop {
        let next = p.GPIO1.data.read().bits() ^ (1 << 0);
        unsafe { p.GPIO1.data.write(|w| w.bits(next)) };
        delay_ms(500);
    }
}

fn delay_ms(ms: u32) {
    let start = systick::millis();
    while systick::millis().wrapping_sub(start) < ms {
        asm::nop();
    }
}
