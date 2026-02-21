#include "lpc111x_min.h"
#include "ssp.h"
#include "uart.h"

void ssp0_init(void)
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

    /* Prescaler must be even and >=2. With 48 MHz PCLK: CPSR=4 => 12 MHz SCK. */
    LPC_SSP0_CPSR = 4u;

    /* Enable SSP0 in master mode. */
    LPC_SSP0_CR1 = (1u << 1);

    uart_puts("SSP0: SR=0x");
    uart_put_hex8((unsigned char)(LPC_SSP0_SR >> 8));
    uart_put_hex8((unsigned char)LPC_SSP0_SR);
    uart_puts("\r\n");
}

uint8_t ssp0_xfer(uint8_t v)
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

void ssp0_cs_low(void)
{
    LPC_GPIO0_DATA &= ~(1u << 2);
}

void ssp0_cs_high(void)
{
    while (LPC_SSP0_SR & (1u << 4)) {
        /* wait not busy */
    }
    LPC_GPIO0_DATA |= (1u << 2);
}
