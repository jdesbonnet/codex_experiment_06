#include "lpc111x_min.h"
#include "uart.h"

void uart_init_57600(void)
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

    /* Baud rate: PCLK=48MHz, divisor=49 with FDR (DIVADD=1, MUL=15). */
    LPC_UART_DLL = 49u;
    LPC_UART_DLM = 0u;

    /* Fractional divider: DIVADD=1, MUL=15. */
    LPC_UART_FDR = 0xF1u;

    /* Disable divisor latch access, keep 8N1. */
    LPC_UART_LCR = 0x3u;

    /* Enable and reset FIFO. */
    LPC_UART_FCR = 0x07u;

    /* Enable transmitter. */
    LPC_UART_TER = 0x80u;
}

void uart_putc(char c)
{
    /* Wait for THR empty. */
    while ((LPC_UART_LSR & (1u << 5)) == 0u) {
        /* spin */
    }
    LPC_UART_THR = (uint32_t)c;
}

void uart_puts(const char *s)
{
    while (*s) {
        uart_putc(*s++);
    }
}

void uart_put_hex8(unsigned char v)
{
    static const char hex[] = "0123456789ABCDEF";
    uart_putc(hex[(v >> 4) & 0xF]);
    uart_putc(hex[v & 0xF]);
}

void uart_put_dec_u32(unsigned int v)
{
    char buf[10];
    int i = 0;
    if (v == 0u) {
        uart_putc('0');
        return;
    }
    while (v > 0u && i < (int)sizeof(buf)) {
        buf[i++] = (char)('0' + (v % 10u));
        v /= 10u;
    }
    while (i-- > 0) {
        uart_putc(buf[i]);
    }
}
