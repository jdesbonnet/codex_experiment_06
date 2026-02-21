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

    uart_puts("UART smoke test\r\n");

    while (1) {
        __asm__ volatile ("wfi");
    }
}
