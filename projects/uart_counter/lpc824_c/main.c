#include <stdbool.h>
#include <stdint.h>

#include "fsl_device_registers.h"

#define UART_BAUD_RATE 230400u
#define PIN_UART_TXD 4u
#define PIN_UART_RXD 0u

static volatile uint32_t g_rx_count;
static volatile uint32_t g_last_rx_byte;

static void usart0_assign_pins(void)
{
    uint32_t reg = SWM0->PINASSIGN.PINASSIGN0;

    reg &= ~(SWM_PINASSIGN0_U0_TXD_O_MASK | SWM_PINASSIGN0_U0_RXD_I_MASK);
    reg |= SWM_PINASSIGN0_U0_TXD_O(PIN_UART_TXD);
    reg |= SWM_PINASSIGN0_U0_RXD_I(PIN_UART_RXD);
    SWM0->PINASSIGN.PINASSIGN0 = reg;
}

static void usart0_configure_baud(uint32_t baud_rate)
{
    uint64_t best_error = UINT64_MAX;
    uint32_t best_brg = 0u;
    uint32_t best_mult = 0u;

    SYSCON->UARTCLKDIV = SYSCON_UARTCLKDIV_DIV(1u);
    SYSCON->UARTFRGDIV = SYSCON_UARTFRGDIV_DIV(0xFFu);

    for (uint32_t mult = 0u; mult <= 0xFFu; ++mult) {
        const uint64_t numerator = (uint64_t)SystemCoreClock * 256u;
        const uint64_t denominator = (uint64_t)(256u + mult) * 16u * baud_rate;
        uint64_t brg_plus_one;
        uint64_t actual_baud;
        uint64_t error;

        if (denominator == 0u) {
            continue;
        }

        brg_plus_one = (numerator + (denominator / 2u)) / denominator;
        if (brg_plus_one == 0u) {
            brg_plus_one = 1u;
        }
        if (brg_plus_one > 65536u) {
            brg_plus_one = 65536u;
        }

        actual_baud = (numerator + (((uint64_t)(256u + mult) * 16u * brg_plus_one) / 2u)) /
                      ((uint64_t)(256u + mult) * 16u * brg_plus_one);

        error = (actual_baud > baud_rate) ? (actual_baud - baud_rate) : (baud_rate - actual_baud);
        if (error < best_error) {
            best_error = error;
            best_brg = (uint32_t)(brg_plus_one - 1u);
            best_mult = mult;
            if (error == 0u) {
                break;
            }
        }
    }

    USART0->OSR = USART_OSR_OSRVAL(15u);
    SYSCON->UARTFRGMULT = SYSCON_UARTFRGMULT_MULT(best_mult);
    USART0->BRG = USART_BRG_BRGVAL(best_brg);
}

static void usart0_init(void)
{
    SYSCON->SYSAHBCLKCTRL |= SYSCON_SYSAHBCLKCTRL_SWM_MASK | SYSCON_SYSAHBCLKCTRL_UART0_MASK;
    SYSCON->PRESETCTRL &= ~(SYSCON_PRESETCTRL_UARTFRG_RST_N_MASK | SYSCON_PRESETCTRL_UART0_RST_N_MASK);
    SYSCON->PRESETCTRL |= SYSCON_PRESETCTRL_UARTFRG_RST_N_MASK | SYSCON_PRESETCTRL_UART0_RST_N_MASK;

    usart0_assign_pins();

    USART0->CFG = USART_CFG_DATALEN(1u) | USART_CFG_PARITYSEL(0u) | USART_CFG_STOPLEN(0u);
    USART0->CTL = 0u;
    usart0_configure_baud(UART_BAUD_RATE);
    USART0->CFG |= USART_CFG_ENABLE_MASK;
}

static void uart_write_byte(uint8_t byte)
{
    while ((USART0->STAT & USART_STAT_TXRDY_MASK) == 0u) {
    }

    USART0->TXDAT = USART_TXDAT_TXDAT(byte);
}

static void uart_write_string(const char *s)
{
    while (*s != '\0') {
        uart_write_byte((uint8_t)*s++);
    }
}

static bool uart_rx_ready(void)
{
    return (USART0->STAT & USART_STAT_RXRDY_MASK) != 0u;
}

static uint8_t uart_read_byte(void)
{
    return (uint8_t)((USART0->RXDAT & USART_RXDAT_RXDAT_MASK) >> USART_RXDAT_RXDAT_SHIFT);
}

int main(void)
{
    SystemCoreClockUpdate();
    usart0_init();

    uart_write_string("LPC824 UART RX latch ready\r\n");

    for (;;) {
        if (uart_rx_ready()) {
            const uint8_t byte = uart_read_byte();
            g_last_rx_byte = byte;
            g_rx_count += 1u;
            uart_write_string("RX ");
            uart_write_byte(byte);
            uart_write_string("\r\n");
        }
    }
}
