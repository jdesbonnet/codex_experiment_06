#include "lpc111x_min.h"
#include "clock.h"
#include "systick.h"
#include "uart.h"

static void delay_ms(uint32_t ms)
{
    uint32_t start = systick_millis();
    while ((systick_millis() - start) < ms) {
        /* spin */
    }
}

int main(void)
{
    const uint32_t pin_mask = (1u << 0);

    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 6) | (1u << 16);
    clock_init_48mhz();
    systick_init_1ms();
    uart_init_57600();

    /* Configure PIO1_0 as GPIO (FUNC=1 for R/PIO1_0). */
    LPC_IOCON_PIO1_0 = (LPC_IOCON_PIO1_0 & ~0x7u) | 0x1u;
    /* Force push-pull: clear OD bit (bit 10). */
    LPC_IOCON_PIO1_0 &= ~(1u << 10);
    LPC_GPIO1_DIR |= pin_mask;

    while (1) {
        LPC_GPIO1_DATA ^= pin_mask;
        uart_puts("PIO1_0=");
        uart_putc((LPC_GPIO1_DATA & pin_mask) ? '1' : '0');
        uart_puts("\r\n");
        delay_ms(500);
    }
}
