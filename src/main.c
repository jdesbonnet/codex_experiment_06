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

static void uart_put_hex8(uint8_t v)
{
    static const char hex[] = "0123456789ABCDEF";
    uart_putc(hex[(v >> 4) & 0xF]);
    uart_putc(hex[v & 0xF]);
}

static void uart_put_hex16(uint16_t v)
{
    uart_put_hex8((uint8_t)(v >> 8));
    uart_put_hex8((uint8_t)v);
}

static void ssp0_init(void)
{
    /* Enable IOCON clock first (required for some LPC111x parts). */
    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 16);

    /* Route SCK0 to PIO0_6. */
    LPC_IOCON_SCK_LOC = (LPC_IOCON_SCK_LOC & ~0x3u) | 0x2u;

    /* Configure SPI0 pins: PIO0_6=SCK0 (FUNC=2), PIO0_8=MISO0 (FUNC=1), PIO0_9=MOSI0 (FUNC=1). */
    LPC_IOCON_PIO0_6 = (LPC_IOCON_PIO0_6 & ~0x7u) | 0x2u;
    LPC_IOCON_PIO0_8 = (LPC_IOCON_PIO0_8 & ~0x7u) | 0x1u;
    LPC_IOCON_PIO0_9 = (LPC_IOCON_PIO0_9 & ~0x7u) | 0x1u;

    /* Use PIO0_2 as GPIO for manual chip select. */
    LPC_IOCON_PIO0_2 &= ~0x7u;
    LPC_GPIO0_DIR |= (1u << 2);
    LPC_GPIO0_DATA |= (1u << 2);

    /* Enable SSP0 clock. */
    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 11);
    LPC_SYSCON_SSP0CLKDIV = 1u;

    /* De-assert SSP0 reset. */
    LPC_SYSCON_PRESETCTRL |= (1u << 0);

    /* Disable SSP0 before configuring. */
    LPC_SSP0_CR1 = 0u;

    /* 8-bit, SPI frame, CPOL=0, CPHA=0, SCR=0. */
    LPC_SSP0_CR0 = 0x7u;

    /* Prescaler must be even and >=2. */
    LPC_SSP0_CPSR = 2u;

    /* Enable SSP0 in master mode. */
    LPC_SSP0_CR1 = (1u << 1);

    uart_puts("SSP0: SR=0x");
    uart_put_hex16((uint16_t)LPC_SSP0_SR);
    uart_puts("\r\n");
}

static uint8_t ssp0_xfer(uint8_t v)
{
    uint32_t timeout = 2000000u;
    while ((LPC_SSP0_SR & (1u << 1)) == 0u) {
        if (--timeout == 0u) {
            uart_puts("SSP0: TNF timeout\r\n");
            return 0u;
        }
    }
    LPC_SSP0_DR = v;
    timeout = 2000000u;
    while ((LPC_SSP0_SR & (1u << 2)) == 0u) {
        if (--timeout == 0u) {
            uart_puts("SSP0: RNE timeout\r\n");
            return 0u;
        }
    }
    return (uint8_t)LPC_SSP0_DR;
}

static void sram_cs_low(void)
{
    LPC_GPIO0_DATA &= ~(1u << 2);
}

static void sram_cs_high(void)
{
    while (LPC_SSP0_SR & (1u << 4)) {
        /* wait not busy */
    }
    LPC_GPIO0_DATA |= (1u << 2);
}

static uint8_t sram_rdmr(void)
{
    uint8_t v;
    sram_cs_low();
    ssp0_xfer(0x05u);
    v = ssp0_xfer(0xFFu);
    sram_cs_high();
    return v;
}

static void sram_wrmr(uint8_t v)
{
    sram_cs_low();
    ssp0_xfer(0x01u);
    ssp0_xfer(v);
    sram_cs_high();
}

static void sram_test(void)
{
    static uint8_t wbuf[256];
    static uint8_t rbuf[256];
    uint8_t mode;
    const uint32_t sram_size = 128u * 1024u;
    const uint32_t chunk = sizeof(wbuf);
    const uint32_t progress_mask = 0x0FFFu;
    const uint8_t patterns[] = { 0x00u, 0xFFu, 0xAAu, 0x55u };

    uart_puts("SRAM: init SPI0\r\n");
    ssp0_init();

    mode = sram_rdmr();
    uart_puts("SRAM: RDMR=");
    uart_put_hex8(mode);
    uart_puts("\r\n");

    /* Force sequential mode for full-memory streaming. */
    sram_wrmr(0x40u);
    mode = sram_rdmr();
    uart_puts("SRAM: RDMR(after WRMR)=");
    uart_put_hex8(mode);
    uart_puts("\r\n");

    uart_puts("SRAM: starting full test\r\n");

    for (uint32_t p = 0; p < sizeof(patterns); p++) {
        uint8_t pat = patterns[p];
        uart_puts("SRAM: pattern 0x");
        uart_put_hex8(pat);
        uart_puts(" write...\r\n");

        sram_cs_low();
        ssp0_xfer(0x02u);
        ssp0_xfer(0x00u);
        ssp0_xfer(0x00u);
        ssp0_xfer(0x00u);
        for (uint32_t addr = 0; addr < sram_size; addr += chunk) {
            for (uint32_t i = 0; i < chunk; i++) {
                wbuf[i] = pat;
                ssp0_xfer(wbuf[i]);
            }
            if ((addr & progress_mask) == 0u) {
                uart_puts("SRAM: write addr=0x");
                uart_put_hex8((uint8_t)(addr >> 16));
                uart_put_hex8((uint8_t)(addr >> 8));
                uart_put_hex8((uint8_t)addr);
                uart_puts("\r\n");
            }
        }
        sram_cs_high();

        uart_puts("SRAM: pattern 0x");
        uart_put_hex8(pat);
        uart_puts(" read/verify...\r\n");

        sram_cs_low();
        ssp0_xfer(0x03u);
        ssp0_xfer(0x00u);
        ssp0_xfer(0x00u);
        ssp0_xfer(0x00u);
        for (uint32_t addr = 0; addr < sram_size; addr += chunk) {
            for (uint32_t i = 0; i < chunk; i++) {
                rbuf[i] = ssp0_xfer(0xFFu);
            }
            for (uint32_t i = 0; i < chunk; i++) {
                if (rbuf[i] != pat) {
                    sram_cs_high();
                    uart_puts("SRAM: mismatch addr=0x");
                    uart_put_hex8((uint8_t)((addr + i) >> 16));
                    uart_put_hex8((uint8_t)((addr + i) >> 8));
                    uart_put_hex8((uint8_t)(addr + i));
                    uart_puts(" exp=");
                    uart_put_hex8(pat);
                    uart_puts(" got=");
                    uart_put_hex8(rbuf[i]);
                    uart_puts("\r\n");
                    return;
                }
            }
            if ((addr & progress_mask) == 0u) {
                uart_puts("SRAM: read  addr=0x");
                uart_put_hex8((uint8_t)(addr >> 16));
                uart_put_hex8((uint8_t)(addr >> 8));
                uart_put_hex8((uint8_t)addr);
                uart_puts("\r\n");
            }
        }
        sram_cs_high();
    }

    uart_puts("SRAM: walking-1s write...\r\n");
    sram_cs_low();
    ssp0_xfer(0x02u);
    ssp0_xfer(0x00u);
    ssp0_xfer(0x00u);
    ssp0_xfer(0x00u);
    for (uint32_t addr = 0; addr < sram_size; addr += chunk) {
        for (uint32_t i = 0; i < chunk; i++) {
            wbuf[i] = (uint8_t)(1u << ((addr + i) & 7u));
            ssp0_xfer(wbuf[i]);
        }
        if ((addr & progress_mask) == 0u) {
            uart_puts("SRAM: write addr=0x");
            uart_put_hex8((uint8_t)(addr >> 16));
            uart_put_hex8((uint8_t)(addr >> 8));
            uart_put_hex8((uint8_t)addr);
            uart_puts("\r\n");
        }
    }
    sram_cs_high();

    uart_puts("SRAM: walking-1s read/verify...\r\n");
    sram_cs_low();
    ssp0_xfer(0x03u);
    ssp0_xfer(0x00u);
    ssp0_xfer(0x00u);
    ssp0_xfer(0x00u);
    for (uint32_t addr = 0; addr < sram_size; addr += chunk) {
        for (uint32_t i = 0; i < chunk; i++) {
            rbuf[i] = ssp0_xfer(0xFFu);
        }
        for (uint32_t i = 0; i < chunk; i++) {
            uint8_t exp = (uint8_t)(1u << ((addr + i) & 7u));
            if (rbuf[i] != exp) {
                sram_cs_high();
                uart_puts("SRAM: mismatch addr=0x");
                uart_put_hex8((uint8_t)((addr + i) >> 16));
                uart_put_hex8((uint8_t)((addr + i) >> 8));
                uart_put_hex8((uint8_t)(addr + i));
                uart_puts(" exp=");
                uart_put_hex8(exp);
                uart_puts(" got=");
                uart_put_hex8(rbuf[i]);
                uart_puts("\r\n");
                return;
            }
        }
        if ((addr & progress_mask) == 0u) {
            uart_puts("SRAM: read  addr=0x");
            uart_put_hex8((uint8_t)(addr >> 16));
            uart_put_hex8((uint8_t)(addr >> 8));
            uart_put_hex8((uint8_t)addr);
            uart_puts("\r\n");
        }
    }
    sram_cs_high();

    uart_puts("SRAM: OK\r\n");
}

int main(void)
{
    /* Enable clocks for GPIO and IOCON blocks. */
    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 6) | (1u << 16);

    uart_init_57600();
    uart_puts("LPC1114 UART at 57600 8N1\r\n");
    sram_test();

    while (1) {
        __asm__ volatile ("wfi");
    }
}
