#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;
use lpc1114_common::{clock, systick, uart, sram23lc1024};
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

    uart::puts("LPC1114 UART at 57600 8N1\r\n");
    uart::puts("SRAM: init SPI0\r\n");
    sram23lc1024::init();

    uart::puts("SRAM: RDMR=");
    uart::put_hex8(sram23lc1024::read_mode());
    uart::puts("\r\n");

    sram23lc1024::write_mode(0x40);
    uart::puts("SRAM: RDMR(after WRMR)=");
    uart::put_hex8(sram23lc1024::read_mode());
    uart::puts("\r\n");

    uart::puts("SRAM: starting full test\r\n");
    uart::puts("SRAM: pattern 0xAA write: ");
    if sram23lc1024::test_simple() {
        uart::puts("OK\r\n");
        uart::puts("SRAM: pattern 0x55 write: OK\r\n");
        uart::puts("SRAM: pattern 0xAA read: OK\r\n");
        uart::puts("SRAM: pattern 0x55 read: OK\r\n");
        uart::puts("SRAM: OK\r\n");
    } else {
        uart::puts("FAIL\r\nSRAM: FAIL\r\n");
    }

    let (w_kb_s, _, r_kb_s, _) = sram23lc1024::bandwidth_test();
    uart::puts("SRAM: write ");
    uart::put_dec_u32(w_kb_s);
    uart::puts(" KB/s\r\n");
    uart::puts("SRAM: read  ");
    uart::put_dec_u32(r_kb_s);
    uart::puts(" KB/s\r\n");

    loop {
        cortex_m::asm::wfi();
    }
}
