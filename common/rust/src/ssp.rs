#![allow(dead_code)]

use crate::pac::Peripherals;
use crate::uart;

pub fn init() {
    let p = unsafe { Peripherals::steal() };

    // Enable IOCON and SSP0 clocks
    unsafe {
        let mut ahb = p.SYSCON.sysahbclkctrl.read().bits();
        ahb |= (1 << 16) | (1 << 11);
        p.SYSCON.sysahbclkctrl.write(|w| w.bits(ahb));
        p.SYSCON.ssp0clkdiv.write(|w| w.bits(1));
        p.SYSCON.presetctrl.write(|w| w.bits(p.SYSCON.presetctrl.read().bits() | 1));
    }

    // Route SCK0 to PIO0_6
    unsafe {
        p.IOCON.iocon_sck0_loc.write(|w| w.bits((p.IOCON.iocon_sck0_loc.read().bits() & !0x3) | 0x2));
    }

    // Configure pins
    unsafe {
        p.IOCON.iocon_pio0_6.write(|w| w.bits((p.IOCON.iocon_pio0_6.read().bits() & !0x7) | 0x2));
        p.IOCON.iocon_pio0_8.write(|w| w.bits((p.IOCON.iocon_pio0_8.read().bits() & !0x7) | 0x1));
        p.IOCON.iocon_pio0_9.write(|w| w.bits((p.IOCON.iocon_pio0_9.read().bits() & !0x7) | 0x1));
        p.IOCON.iocon_pio0_2.write(|w| w.bits(p.IOCON.iocon_pio0_2.read().bits() & !0x7));
        p.GPIO0.dir.write(|w| w.bits(p.GPIO0.dir.read().bits() | (1 << 2)));
        p.GPIO0.data.write(|w| w.bits(p.GPIO0.data.read().bits() | (1 << 2)));
    }

    unsafe {
        p.SPI0.cr1.write(|w| w.bits(0));
        p.SPI0.cr0.write(|w| w.bits(0x7));
        p.SPI0.cpsr.write(|w| w.bits(4));
        p.SPI0.cr1.write(|w| w.bits(1 << 1));
    }

    uart::puts("SSP0: SR=0x");
    let sr = p.SPI0.sr.read().bits() as u16;
    uart::put_hex8((sr >> 8) as u8);
    uart::put_hex8(sr as u8);
    uart::puts("\r\n");
}

pub fn xfer(v: u8) -> u8 {
    let p = unsafe { Peripherals::steal() };
    let mut timeout = 2_000_000u32;
    while (p.SPI0.sr.read().bits() & (1 << 1)) == 0 {
        timeout -= 1;
        if timeout == 0 {
            uart::puts("SSP0: TNF timeout\r\n");
            return 0;
        }
    }
    unsafe { p.SPI0.dr.write(|w| w.bits(v as u32)) };
    timeout = 2_000_000u32;
    while (p.SPI0.sr.read().bits() & (1 << 2)) == 0 {
        timeout -= 1;
        if timeout == 0 {
            uart::puts("SSP0: RNE timeout\r\n");
            return 0;
        }
    }
    p.SPI0.dr.read().bits() as u8
}

pub fn cs_low() {
    let p = unsafe { Peripherals::steal() };
    unsafe { p.GPIO0.data.write(|w| w.bits(p.GPIO0.data.read().bits() & !(1 << 2))) };
}

pub fn cs_high() {
    let p = unsafe { Peripherals::steal() };
    while (p.SPI0.sr.read().bits() & (1 << 4)) != 0 {}
    unsafe { p.GPIO0.data.write(|w| w.bits(p.GPIO0.data.read().bits() | (1 << 2))) };
}
