/* LPC1114FN28/102 linker script
 * Flash: 32 KB @ 0x00000000
 * SRAM: 4 KB @ 0x10000000
 * Reference: LPC111x datasheet Rev 9.2, table shows LPC1114/102 = 32 kB flash, 4 kB SRAM.
 */

MEMORY
{
  FLASH (rx) : ORIGIN = 0x00000000, LENGTH = 32K
  RAM (rwx)  : ORIGIN = 0x10000000, LENGTH = 4K
}

ENTRY(Reset_Handler)

SECTIONS
{
  .isr_vector :
  {
    KEEP(*(.isr_vector))
  } > FLASH

  .text :
  {
    *(.text*)
    *(.rodata*)
    KEEP(*(.init))
    KEEP(*(.fini))
  } > FLASH

  .ARM.exidx :
  {
    *(.ARM.exidx*)
  } > FLASH

  .data : AT (ADDR(.text) + SIZEOF(.text))
  {
    _sdata = .;
    *(.data*)
    _edata = .;
  } > RAM

  .bss :
  {
    _sbss = .;
    *(.bss*)
    *(COMMON)
    _ebss = .;
  } > RAM

  _sidata = LOADADDR(.data);
  _estack = ORIGIN(RAM) + LENGTH(RAM);
}
