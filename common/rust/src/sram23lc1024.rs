#![allow(dead_code)]

use crate::systick;
use crate::ssp;

pub fn init() {
    ssp::init();
}

pub fn read_mode() -> u8 {
    let v;
    ssp::cs_low();
    ssp::xfer(0x05);
    v = ssp::xfer(0xFF);
    ssp::cs_high();
    v
}

pub fn write_mode(v: u8) {
    ssp::cs_low();
    ssp::xfer(0x01);
    ssp::xfer(v);
    ssp::cs_high();
}

pub fn test_simple() -> bool {
    const SRAM_SIZE: u32 = 128 * 1024;
    const CHUNK: usize = 256;
    let patterns = [0xAAu8, 0x55u8];
    let mut wbuf = [0u8; CHUNK];
    let mut rbuf = [0u8; CHUNK];

    for pat in patterns.iter() {
        ssp::cs_low();
        ssp::xfer(0x02);
        ssp::xfer(0x00);
        ssp::xfer(0x00);
        ssp::xfer(0x00);
        let mut addr = 0u32;
        while addr < SRAM_SIZE {
            for i in 0..CHUNK {
                wbuf[i] = *pat;
                ssp::xfer(wbuf[i]);
            }
            addr += CHUNK as u32;
        }
        ssp::cs_high();

        ssp::cs_low();
        ssp::xfer(0x03);
        ssp::xfer(0x00);
        ssp::xfer(0x00);
        ssp::xfer(0x00);
        addr = 0u32;
        while addr < SRAM_SIZE {
            for i in 0..CHUNK {
                rbuf[i] = ssp::xfer(0xFF);
            }
            for i in 0..CHUNK {
                if rbuf[i] != *pat {
                    ssp::cs_high();
                    return false;
                }
            }
            addr += CHUNK as u32;
        }
        ssp::cs_high();
    }

    true
}

pub fn bandwidth_test() -> (u32, u32, u32, u32) {
    const SRAM_SIZE: u32 = 128 * 1024;
    const CHUNK: u32 = 256;
    let mut start = systick::millis();
    let mut elapsed;

    // Write bandwidth
    ssp::cs_low();
    ssp::xfer(0x02);
    ssp::xfer(0x00);
    ssp::xfer(0x00);
    ssp::xfer(0x00);
    let mut addr = 0u32;
    while addr < SRAM_SIZE {
        let mut i = 0u32;
        while i < CHUNK {
            ssp::xfer(0x00);
            i += 1;
        }
        addr += CHUNK;
    }
    ssp::cs_high();
    elapsed = systick::millis().wrapping_sub(start);
    if elapsed == 0 { elapsed = 1; }
    let write_kb_s = (SRAM_SIZE * 1000 / elapsed) / 1024;

    // Read bandwidth
    start = systick::millis();
    ssp::cs_low();
    ssp::xfer(0x03);
    ssp::xfer(0x00);
    ssp::xfer(0x00);
    ssp::xfer(0x00);
    addr = 0;
    while addr < SRAM_SIZE {
        let mut i = 0u32;
        while i < CHUNK {
            let _ = ssp::xfer(0xFF);
            i += 1;
        }
        addr += CHUNK;
    }
    ssp::cs_high();
    elapsed = systick::millis().wrapping_sub(start);
    if elapsed == 0 { elapsed = 1; }
    let read_kb_s = (SRAM_SIZE * 1000 / elapsed) / 1024;

    (write_kb_s, 0, read_kb_s, 0)
}
