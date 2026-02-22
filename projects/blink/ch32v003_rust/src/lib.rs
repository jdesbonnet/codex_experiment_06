#![no_std]

use ch32v0::ch32v003::Peripherals;
use panic_halt as _;

#[no_mangle]
pub extern "C" fn rust_blink_main() -> ! {
    let p = unsafe { Peripherals::steal() };

    // Enable GPIOD peripheral clock.
    p.RCC.apb2pcenr().modify(|_, w| w.iopden().set_bit());

    // Configure PD4 as push-pull output, 10 MHz (MODE=0b01, CNF=0b00).
    p.GPIOD.cfglr().modify(|r, w| unsafe {
        let bits = (r.bits() & !(0xF << 16)) | (0x1 << 16);
        w.bits(bits)
    });

    loop {
        p.GPIOD.bshr().write(|w| w.bs4().set_bit());
        delay(300_000);
        p.GPIOD.bshr().write(|w| w.br4().set_bit());
        delay(300_000);
    }
}

#[inline(never)]
fn delay(mut cycles: u32) {
    while cycles != 0 {
        unsafe { core::arch::asm!("nop") };
        cycles -= 1;
    }
}
