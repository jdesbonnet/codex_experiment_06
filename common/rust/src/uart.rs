#![allow(dead_code)]

use crate::pac::Peripherals;

pub fn init_57600() {
    let p = unsafe { Peripherals::steal() };

    // Enable IOCON and UART clocks
    unsafe {
        let mut ahb = p.SYSCON.sysahbclkctrl.read().bits();
        ahb |= (1 << 16) | (1 << 12);
        p.SYSCON.sysahbclkctrl.write(|w| w.bits(ahb));
    }

    // Select RXD/TXD on PIO1_6/PIO1_7, push-pull.
    unsafe {
        let mut v6 = p.IOCON.iocon_pio1_6.read().bits();
        v6 = (v6 & !0x7) | 0x1;
        v6 &= !(1 << 10);
        p.IOCON.iocon_pio1_6.write(|w| w.bits(v6));

        let mut v7 = p.IOCON.iocon_pio1_7.read().bits();
        v7 = (v7 & !0x7) | 0x1;
        v7 &= !(1 << 10);
        p.IOCON.iocon_pio1_7.write(|w| w.bits(v7));
    }

    // UART clock divider / 8N1 + DLAB
    unsafe {
        p.SYSCON.uartclkdiv.write(|w| w.bits(1));
        p.UART.lcr.write(|w| w.bits((1 << 7) | 0x3));
        // Derive a coarse PCLK estimate from SYSCON; fall back to 12 MHz.
        let main_sel = p.SYSCON.mainclksel.read().bits() & 0x3;
        let pll_locked = (p.SYSCON.syspllstat.read().bits() & 0x1) != 0;
        let ahb_div = p.SYSCON.sysahbclkdiv.read().bits() & 0xFF;
        let base_hz = if main_sel == 3 && pll_locked { 48_000_000u32 } else { 12_000_000u32 };
        let div = if ahb_div == 0 { 1 } else { ahb_div };
        let pclk_hz = base_hz / div;

        if pclk_hz >= 48_000_000 {
            // Baud rate: PCLK=48MHz, divisor=49 with FDR (DIVADD=1, MUL=15).
            p.UART.dll().write(|w| w.bits(49));
            p.UART.dlm().write(|w| w.bits(0));
            p.UART.fdr.write(|w| w.bits(0xF1));
        } else {
            // Baud rate: PCLK=12MHz, divisor=13 with FDR (DIVADD=1, MUL=15).
            p.UART.dll().write(|w| w.bits(13));
            p.UART.dlm().write(|w| w.bits(0));
            p.UART.fdr.write(|w| w.bits(0xF1));
        }
        p.UART.lcr.write(|w| w.bits(0x3));
        p.UART.fcr().write(|w| w.bits(0x07));
        p.UART.ter.write(|w| w.bits(0x80));
    }
}

pub fn putc(c: u8) {
    let p = unsafe { Peripherals::steal() };
    while (p.UART.lsr.read().bits() & (1 << 5)) == 0 {}
    unsafe { p.UART.thr().write(|w| w.bits(c as u32)) };
}

pub fn puts(s: &str) {
    for b in s.as_bytes() {
        putc(*b);
    }
}

pub fn put_hex8(v: u8) {
    const HEX: &[u8; 16] = b"0123456789ABCDEF";
    putc(HEX[(v >> 4) as usize]);
    putc(HEX[(v & 0xF) as usize]);
}

pub fn put_dec_u32(mut v: u32) {
    let mut buf = [0u8; 10];
    if v == 0 {
        putc(b'0');
        return;
    }
    let mut i = 0;
    while v > 0 && i < buf.len() {
        buf[i] = b'0' + (v % 10) as u8;
        v /= 10;
        i += 1;
    }
    while i > 0 {
        i -= 1;
        putc(buf[i]);
    }
}
