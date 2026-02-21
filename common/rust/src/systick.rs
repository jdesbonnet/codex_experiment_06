#![allow(dead_code)]

use cortex_m_rt::exception;
use core::ptr;

static mut MS: u32 = 0;

pub fn init_1ms() {
    // 48 MHz system clock -> 1 ms tick
    unsafe {
        let syst = &mut *(0xE000E010 as *mut u32); // CSR
        let rvr = &mut *(0xE000E014 as *mut u32);
        let cvr = &mut *(0xE000E018 as *mut u32);
        *rvr = 48000 - 1;
        *cvr = 0;
        *syst = (1 << 0) | (1 << 1) | (1 << 2);
    }
}

pub fn init_1ms_12mhz() {
    // 12 MHz system clock -> 1 ms tick
    unsafe {
        let syst = &mut *(0xE000E010 as *mut u32); // CSR
        let rvr = &mut *(0xE000E014 as *mut u32);
        let cvr = &mut *(0xE000E018 as *mut u32);
        *rvr = 12000 - 1;
        *cvr = 0;
        *syst = (1 << 0) | (1 << 1) | (1 << 2);
    }
}

pub fn millis() -> u32 {
    unsafe { ptr::read_volatile(&raw const MS) }
}

#[exception]
fn SysTick() {
    unsafe {
        let v = ptr::read_volatile(&raw const MS);
        ptr::write_volatile(&raw mut MS, v.wrapping_add(1));
    }
}
