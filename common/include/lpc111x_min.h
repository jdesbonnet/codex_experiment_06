#ifndef LPC111X_MIN_H
#define LPC111X_MIN_H

#include <stdint.h>

/* Minimal register definitions for LPC111x.
 * Reference: UM10398 (LPC1100/LPC1100L user manual).
 */

#define LPC_SYSCON_BASE      0x40048000u
#define LPC_IOCON_BASE       0x40044000u
#define LPC_GPIO_BASE        0x50000000u
#define LPC_GPIO1_BASE       0x50010000u
#define LPC_UART_BASE        0x40008000u
#define LPC_SSP0_BASE        0x40040000u
#define LPC_PMU_BASE         0x40038000u
#define LPC_CT32B0_BASE      0x40014000u
#define LPC_CT16B0_BASE      0x4000C000u

/* Cortex-M0 SysTick registers. */
#define SYST_CSR            (*(volatile uint32_t *)(0xE000E010u))
#define SYST_RVR            (*(volatile uint32_t *)(0xE000E014u))
#define SYST_CVR            (*(volatile uint32_t *)(0xE000E018u))
#define SCB_SCR             (*(volatile uint32_t *)(0xE000ED10u))
#define NVIC_ISER0          (*(volatile uint32_t *)(0xE000E100u))
#define NVIC_ICER0          (*(volatile uint32_t *)(0xE000E180u))
#define NVIC_ICPR0          (*(volatile uint32_t *)(0xE000E280u))

#define LPC_SYSCON_SYSAHBCLKCTRL   (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x080))
#define LPC_SYSCON_SYSPLLCLKSEL    (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x040))
#define LPC_SYSCON_SYSPLLCLKUEN    (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x044))
#define LPC_SYSCON_MAINCLKSEL      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x070))
#define LPC_SYSCON_MAINCLKUEN      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x074))
#define LPC_SYSCON_SYSAHBCLKDIV    (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x078))
#define LPC_SYSCON_SYSOSCCTRL      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x020))
#define LPC_SYSCON_SYSPLLCTRL      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x008))
#define LPC_SYSCON_SYSPLLSTAT      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x00C))
#define LPC_SYSCON_PRESETCTRL      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x004))
#define LPC_SYSCON_WDTOSCCTRL      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x024))
#define LPC_SYSCON_SYSRSTSTAT      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x030))
#define LPC_SYSCON_PDRUNCFG        (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x238))
#define LPC_SYSCON_PDSLEEPCFG      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x230))
#define LPC_SYSCON_PDAWAKECFG      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x234))
#define LPC_SYSCON_UARTCLKDIV      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x098))
#define LPC_SYSCON_SSP0CLKDIV      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x094))
#define LPC_SYSCON_WDTCLKSEL       (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x0D0))
#define LPC_SYSCON_WDTCLKUEN       (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x0D4))
#define LPC_SYSCON_WDTCLKDIV       (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x0D8))
#define LPC_SYSCON_STARTAPRP0      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x200))
#define LPC_SYSCON_STARTERP0       (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x204))
#define LPC_SYSCON_STARTRSRP0CLR   (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x208))
#define LPC_SYSCON_STARTSRP0       (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x20C))

#define LPC_GPIO0_DIR               (*(volatile uint32_t *)(LPC_GPIO_BASE + 0x8000))
#define LPC_GPIO0_DATA              (*(volatile uint32_t *)(LPC_GPIO_BASE + 0x3FFC))

#define LPC_GPIO1_DIR               (*(volatile uint32_t *)(LPC_GPIO1_BASE + 0x8000))
#define LPC_GPIO1_DATA              (*(volatile uint32_t *)(LPC_GPIO1_BASE + 0x3FFC))

/* IOCON register for PIO1_2 (address 0x4004 4080) */
#define LPC_IOCON_PIO1_2            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x080))

/* IOCON registers for UART pins (PIO1_6 RXD, PIO1_7 TXD). */
#define LPC_IOCON_PIO1_6            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x0A4))
#define LPC_IOCON_PIO1_7            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x0A8))

/* IOCON register for PIO1_0 (address 0x4004 4078). */
#define LPC_IOCON_PIO1_0            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x078))
/* IOCON register for PIO0_1 (address 0x4004 4010). */
#define LPC_IOCON_PIO0_1            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x010))

/* IOCON registers for SPI0 pins. */
#define LPC_IOCON_PIO0_2            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x01C))
#define LPC_IOCON_PIO0_6            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x04C))
#define LPC_IOCON_PIO0_8            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x060))
#define LPC_IOCON_PIO0_9            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x064))
#define LPC_IOCON_SCK_LOC           (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x0B0))

/* UART0 registers. */
#define LPC_UART_RBR                (*(volatile uint32_t *)(LPC_UART_BASE + 0x000))
#define LPC_UART_THR                (*(volatile uint32_t *)(LPC_UART_BASE + 0x000))
#define LPC_UART_DLL                (*(volatile uint32_t *)(LPC_UART_BASE + 0x000))
#define LPC_UART_DLM                (*(volatile uint32_t *)(LPC_UART_BASE + 0x004))
#define LPC_UART_IER                (*(volatile uint32_t *)(LPC_UART_BASE + 0x004))
#define LPC_UART_FCR                (*(volatile uint32_t *)(LPC_UART_BASE + 0x008))
#define LPC_UART_LCR                (*(volatile uint32_t *)(LPC_UART_BASE + 0x00C))
#define LPC_UART_LSR                (*(volatile uint32_t *)(LPC_UART_BASE + 0x014))
#define LPC_UART_FDR                (*(volatile uint32_t *)(LPC_UART_BASE + 0x028))
#define LPC_UART_TER                (*(volatile uint32_t *)(LPC_UART_BASE + 0x030))

/* SSP0 registers. */
#define LPC_SSP0_CR0                (*(volatile uint32_t *)(LPC_SSP0_BASE + 0x000))
#define LPC_SSP0_CR1                (*(volatile uint32_t *)(LPC_SSP0_BASE + 0x004))
#define LPC_SSP0_DR                 (*(volatile uint32_t *)(LPC_SSP0_BASE + 0x008))
#define LPC_SSP0_SR                 (*(volatile uint32_t *)(LPC_SSP0_BASE + 0x00C))
#define LPC_SSP0_CPSR               (*(volatile uint32_t *)(LPC_SSP0_BASE + 0x010))

/* CT32B0 timer registers. */
#define LPC_CT32B0_IR               (*(volatile uint32_t *)(LPC_CT32B0_BASE + 0x000))
#define LPC_CT32B0_TCR              (*(volatile uint32_t *)(LPC_CT32B0_BASE + 0x004))
#define LPC_CT32B0_TC               (*(volatile uint32_t *)(LPC_CT32B0_BASE + 0x008))
#define LPC_CT32B0_PR               (*(volatile uint32_t *)(LPC_CT32B0_BASE + 0x00C))
#define LPC_CT32B0_PC               (*(volatile uint32_t *)(LPC_CT32B0_BASE + 0x010))
#define LPC_CT32B0_MCR              (*(volatile uint32_t *)(LPC_CT32B0_BASE + 0x014))
#define LPC_CT32B0_MR0              (*(volatile uint32_t *)(LPC_CT32B0_BASE + 0x018))
#define LPC_CT32B0_MR2              (*(volatile uint32_t *)(LPC_CT32B0_BASE + 0x020))
#define LPC_CT32B0_EMR              (*(volatile uint32_t *)(LPC_CT32B0_BASE + 0x03C))

/* CT16B0 timer registers. */
#define LPC_CT16B0_IR               (*(volatile uint32_t *)(LPC_CT16B0_BASE + 0x000))
#define LPC_CT16B0_TCR              (*(volatile uint32_t *)(LPC_CT16B0_BASE + 0x004))
#define LPC_CT16B0_TC               (*(volatile uint32_t *)(LPC_CT16B0_BASE + 0x008))
#define LPC_CT16B0_PR               (*(volatile uint32_t *)(LPC_CT16B0_BASE + 0x00C))
#define LPC_CT16B0_PC               (*(volatile uint32_t *)(LPC_CT16B0_BASE + 0x010))
#define LPC_CT16B0_MCR              (*(volatile uint32_t *)(LPC_CT16B0_BASE + 0x014))
#define LPC_CT16B0_MR0              (*(volatile uint32_t *)(LPC_CT16B0_BASE + 0x018))
#define LPC_CT16B0_EMR              (*(volatile uint32_t *)(LPC_CT16B0_BASE + 0x03C))

/* PMU registers. */
#define LPC_PMU_PCON                (*(volatile uint32_t *)(LPC_PMU_BASE + 0x000))
#define LPC_PMU_GPREG0              (*(volatile uint32_t *)(LPC_PMU_BASE + 0x004))

/* Watchdog registers. */
#define LPC_WDT_BASE                0x40004000u
#define LPC_WDT_WDMOD               (*(volatile uint32_t *)(LPC_WDT_BASE + 0x000))
#define LPC_WDT_WDTC                (*(volatile uint32_t *)(LPC_WDT_BASE + 0x004))
#define LPC_WDT_WDFEED              (*(volatile uint32_t *)(LPC_WDT_BASE + 0x008))
#define LPC_WDT_WDTV                (*(volatile uint32_t *)(LPC_WDT_BASE + 0x00C))
#define LPC_WDT_WDWARNINT           (*(volatile uint32_t *)(LPC_WDT_BASE + 0x014))
#define LPC_WDT_WDWINDOW            (*(volatile uint32_t *)(LPC_WDT_BASE + 0x018))

#endif
