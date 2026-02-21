#include "lpc111x_min.h"
#include "clock.h"
#include "systick.h"
#include "uart.h"
#include "sram23lc1024.h"

int main(void)
{
    /* Enable clocks for GPIO and IOCON blocks. */
    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 6) | (1u << 16);

    clock_init_48mhz();
    systick_init_1ms();
    uart_init_57600();

    uart_puts("LPC1114 UART at 57600 8N1\r\n");

    uart_puts("SRAM: init SPI0\r\n");
    sram_init();

    uart_puts("SRAM: RDMR=");
    uart_put_hex8(sram_read_mode());
    uart_puts("\r\n");

    sram_write_mode(0x40u);
    uart_puts("SRAM: RDMR(after WRMR)=");
    uart_put_hex8(sram_read_mode());
    uart_puts("\r\n");

    uart_puts("SRAM: starting full test\r\n");
    uart_puts("SRAM: pattern 0xAA write: ");
    if (sram_test_simple() == 0) {
        uart_puts("OK\r\n");
        uart_puts("SRAM: pattern 0x55 write: OK\r\n");
        uart_puts("SRAM: pattern 0xAA read: OK\r\n");
        uart_puts("SRAM: pattern 0x55 read: OK\r\n");
        uart_puts("SRAM: OK\r\n");
    } else {
        uart_puts("FAIL\r\n");
        uart_puts("SRAM: FAIL\r\n");
    }

    uart_puts("SRAM: bandwidth test\r\n");
    {
        uint32_t w_kb_s = 0u, w_ms = 0u, r_kb_s = 0u, r_ms = 0u;
        sram_bandwidth_test(&w_kb_s, &w_ms, &r_kb_s, &r_ms);
        uart_puts("SRAM: write ");
        uart_put_dec_u32(w_kb_s);
        uart_puts(" KB/s (");
        uart_put_dec_u32(w_ms);
        uart_puts(" ms)\r\n");
        uart_puts("SRAM: read  ");
        uart_put_dec_u32(r_kb_s);
        uart_puts(" KB/s (");
        uart_put_dec_u32(r_ms);
        uart_puts(" ms)\r\n");
    }

    while (1) {
        __asm__ volatile ("wfi");
    }
}
