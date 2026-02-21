#include <stdint.h>
#include "lpc111x_min.h"

/*
 * Minimal main loop. Blinks PIO1_2 at ~2 Hz and prints a UART message.
 * Assumes default IRC clock (~12 MHz) and no PLL configuration.
 * References:
 * - UM10398 SYSAHBCLKCTRL bits 6 (GPIO), 12 (UART), 16 (IOCON).
 * - IOCON_PIO1_2 at 0x4004 4080.
 * - IOCON_PIO1_6 (RXD) at 0x4004 40A4, IOCON_PIO1_7 (TXD) at 0x4004 40A8.
 * - UART base 0x4000 8000, UARTCLKDIV at 0x4004 8098.
 */

static void uart_init_57600(void)
{
    /* Enable IOCON clock first (required for some LPC111x parts). */
    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 16);

    /* Select RXD/TXD function on PIO1_6 and PIO1_7 (FUNC = 1). */
    LPC_IOCON_PIO1_6 = (LPC_IOCON_PIO1_6 & ~0x7u) | 0x1u;
    LPC_IOCON_PIO1_7 = (LPC_IOCON_PIO1_7 & ~0x7u) | 0x1u;

    /* Enable UART clock. */
    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 12);

    /* UART peripheral clock divider: divide by 1. */
    LPC_SYSCON_UARTCLKDIV = 1u;

    /* 8N1, enable access to divisor latches. */
    LPC_UART_LCR = (1u << 7) | 0x3u;

    /* Baud rate: PCLK=12MHz, divisor=13 -> 12e6/(16*13) ≈ 57692. */
    LPC_UART_DLL = 13u;
    LPC_UART_DLM = 0u;

    /* Fractional divider: no fraction (DIVADD=0, MUL=1). */
    LPC_UART_FDR = 0x10u;

    /* Disable divisor latch access, keep 8N1. */
    LPC_UART_LCR = 0x3u;

    /* Enable and reset FIFO. */
    LPC_UART_FCR = 0x07u;

    /* Enable transmitter. */
    LPC_UART_TER = 0x80u;
}

static void uart_putc(char c)
{
    /* Wait for THR empty. */
    while ((LPC_UART_LSR & (1u << 5)) == 0u) {
        /* spin */
    }
    LPC_UART_THR = (uint32_t)c;
}

static void uart_puts(const char *s)
{
    while (*s) {
        uart_putc(*s++);
    }
}

int main(void)
{
    const uint32_t pin_mask = (1u << 2);

    /* Enable clocks for GPIO and IOCON blocks. */
    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 6) | (1u << 16);

    /* Select GPIO function for PIO1_2 (FUNC = 0). */
    LPC_IOCON_PIO1_2 &= ~0x7u;

    /* Set PIO1_2 as output. */
    LPC_GPIO1_DIR |= pin_mask;

    uart_init_57600();
    uart_puts("LPC1114 UART at 57600 8N1\r\n");

    while (1) {
        uart_puts("tick\r\n");
        LPC_GPIO1_DATA ^= pin_mask;

        /* Rough delay for ~2 Hz blink at ~12 MHz.
         * Adjust delay count if system clock changes.
         */
        for (volatile uint32_t i = 0; i < 600000u; i++) {
            __asm__ volatile ("nop");
        }
    }
}
