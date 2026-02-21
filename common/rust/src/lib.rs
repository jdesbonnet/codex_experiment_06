#![no_std]

pub mod clock;
pub mod systick;
pub mod uart;
pub mod ssp;
pub mod sram23lc1024;

// Re-export PAC
pub use lpc11xx as pac;
