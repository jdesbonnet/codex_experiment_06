#include "lpc111x_min.h"
#include "clock.h"
#include "systick.h"
#include "uart.h"

int main(void)
{
    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 6) | (1u << 16);
    clock_init_48mhz();
    systick_init_1ms();
    uart_init_57600();

    unsigned int counter = 0;
    while (1) {
        uart_puts("C test ");
        uart_put_dec_u32(counter);
        uart_puts("\r\n");
        counter++;
        uint32_t start = systick_millis();
        while ((uint32_t)(systick_millis() - start) < 1000u) {
            /* spin */
        }
    }
}
