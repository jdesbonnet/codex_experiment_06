#![allow(dead_code)]

use crate::pac::Peripherals;

pub fn init_48mhz() {
    let p = unsafe { Peripherals::steal() };

    // Power up SYSPLL and ensure IRC is powered; keep reserved bits as in UM10398 Table 44.
    let mut pdruncfg = p.SYSCON.pdruncfg.read().bits();
    pdruncfg &= !((1 << 7) | (1 << 1) | (1 << 0));
    pdruncfg |= (1 << 8) | (1 << 10) | (1 << 11) | (7 << 13);
    pdruncfg &= !((1 << 9) | (1 << 12));
    unsafe { p.SYSCON.pdruncfg.write(|w| w.bits(pdruncfg)) };

    // Select IRC as PLL source and update.
    unsafe {
        p.SYSCON.syspllclksel.write(|w| w.bits(0));
        p.SYSCON.syspllclkuen.write(|w| w.bits(0));
        p.SYSCON.syspllclkuen.write(|w| w.bits(1));
    }
    while (p.SYSCON.syspllclkuen.read().bits() & 0x1) == 0 {}

    // Configure PLL: M = 4 (MSEL=3), P = 2 (PSEL=1).
    unsafe { p.SYSCON.syspllctrl.write(|w| w.bits((3 << 0) | (1 << 5))) };

    // Wait for PLL lock.
    while p.SYSCON.syspllstat.read().bits() & 0x1 == 0 {}

    // Main clock = SYSPLL clock out.
    unsafe {
        p.SYSCON.mainclksel.write(|w| w.bits(3));
        p.SYSCON.mainclkuen.write(|w| w.bits(0));
        p.SYSCON.mainclkuen.write(|w| w.bits(1));
        p.SYSCON.sysahbclkdiv.write(|w| w.bits(1));
    }
    while (p.SYSCON.mainclkuen.read().bits() & 0x1) == 0 {}
}
