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

#define LPC_SYSCON_SYSAHBCLKCTRL   (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x080))
#define LPC_SYSCON_SYSPLLCLKSEL    (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x040))
#define LPC_SYSCON_SYSPLLCLKUEN    (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x044))
#define LPC_SYSCON_MAINCLKSEL      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x070))
#define LPC_SYSCON_MAINCLKUEN      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x074))
#define LPC_SYSCON_SYSOSCCTRL      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x020))
#define LPC_SYSCON_SYSPLLCTRL      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x008))
#define LPC_SYSCON_SYSPLLSTAT      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x00C))
#define LPC_SYSCON_UARTCLKDIV      (*(volatile uint32_t *)(LPC_SYSCON_BASE + 0x098))

#define LPC_GPIO0_DIR               (*(volatile uint32_t *)(LPC_GPIO_BASE + 0x8000))
#define LPC_GPIO0_DATA              (*(volatile uint32_t *)(LPC_GPIO_BASE + 0x3FFC))

#define LPC_GPIO1_DIR               (*(volatile uint32_t *)(LPC_GPIO1_BASE + 0x8000))
#define LPC_GPIO1_DATA              (*(volatile uint32_t *)(LPC_GPIO1_BASE + 0x3FFC))

/* IOCON register for PIO1_2 (address 0x4004 4080) */
#define LPC_IOCON_PIO1_2            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x080))

/* IOCON registers for UART pins (PIO1_6 RXD, PIO1_7 TXD). */
#define LPC_IOCON_PIO1_6            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x0A4))
#define LPC_IOCON_PIO1_7            (*(volatile uint32_t *)(LPC_IOCON_BASE + 0x0A8))

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

#endif
