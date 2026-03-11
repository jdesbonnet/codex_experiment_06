#include <stdint.h>

#include "tm4c123gh6pm.h"

/*
 * UART0 counter demo for the EK-TM4C123GXL LaunchPad.
 *
 * Board routing reference:
 *   The on-board ICDI exposes a virtual COM port on the host USB link.
 *   Per EK-TM4C123GXL user manual section 2.3.1, that VCP is wired to
 *   PA0/U0RX and PA1/U0TX on the target MCU.
 *
 * Clocking reference:
 *   UART0 is sourced from the 16 MHz precision internal oscillator (PIOSC)
 *   by setting UARTCC.CS = 0x5. The baud-rate divisors below follow the
 *   TM4C123 UART baud formula:
 *     BRD = UARTClk / (16 * Baud)
 *   For 115200 baud with a 16 MHz UART clock:
 *     BRD = 8.680555..., so IBRD = 8 and FBRD = round(0.680555 * 64) = 44
 */

#define UART_BAUD_115200_IBRD 8u
#define UART_BAUD_115200_FBRD 44u

static volatile uint32_t g_ms_ticks;

void SysTick_Handler(void)
{
    g_ms_ticks++;
}

static void delay_ms(uint32_t delay_ms)
{
    uint32_t start = g_ms_ticks;
    while ((uint32_t)(g_ms_ticks - start) < delay_ms) {
        /* Wait for the SysTick timebase to advance. */
    }
}

static void systick_init_1ms(void)
{
    NVIC_ST_RELOAD_R = 16000u - 1u;
    NVIC_ST_CURRENT_R = 0u;
    NVIC_ST_CTRL_R = NVIC_ST_CTRL_CLK_SRC | NVIC_ST_CTRL_INTEN | NVIC_ST_CTRL_ENABLE;
}

static void uart0_init_115200(void)
{
    SYSCTL_RCGCGPIO_R |= (1u << TM4C123_PORTA_BIT);
    SYSCTL_RCGCUART_R |= (1u << 0);

    while ((SYSCTL_PRGPIO_R & (1u << TM4C123_PORTA_BIT)) == 0u) {
        /* Wait until GPIO Port A leaves reset. */
    }
    while ((SYSCTL_PRUART_R & (1u << 0)) == 0u) {
        /* Wait until UART0 leaves reset. */
    }

    UART0_CTL_R &= ~(UART_CTL_UARTEN | UART_CTL_TXE | UART_CTL_RXE);
    UART0_CC_R = UART_CC_CS_PIOSC;
    UART0_IBRD_R = UART_BAUD_115200_IBRD;
    UART0_FBRD_R = UART_BAUD_115200_FBRD;
    UART0_LCRH_R = UART_LCRH_WLEN_8 | UART_LCRH_FEN;

    GPIO_PORTA_AMSEL_R &= ~(TM4C123_PA0_U0RX | TM4C123_PA1_U0TX);
    GPIO_PORTA_PCTL_R &= ~0x000000FFu;
    GPIO_PORTA_PCTL_R |= 0x00000011u;
    GPIO_PORTA_AFSEL_R |= TM4C123_PA0_U0RX | TM4C123_PA1_U0TX;
    GPIO_PORTA_DEN_R |= TM4C123_PA0_U0RX | TM4C123_PA1_U0TX;
    GPIO_PORTA_DR2R_R |= TM4C123_PA1_U0TX;
    GPIO_PORTA_DIR_R &= ~TM4C123_PA0_U0RX;
    GPIO_PORTA_DIR_R |= TM4C123_PA1_U0TX;

    UART0_CTL_R = UART_CTL_UARTEN | UART_CTL_TXE | UART_CTL_RXE;
}

static void uart0_putc(char ch)
{
    while ((UART0_FR_R & UART_FR_TXFF) != 0u) {
        /* Wait for space in the transmit FIFO. */
    }
    UART0_DR_R = (uint32_t)(uint8_t)ch;
}

static void uart0_puts(const char *text)
{
    while (*text != '\0') {
        uart0_putc(*text++);
    }
}

static void uart0_put_dec_u32(uint32_t value)
{
    char buffer[10];
    uint32_t i = 0u;

    if (value == 0u) {
        uart0_putc('0');
        return;
    }

    while (value != 0u) {
        buffer[i++] = (char)('0' + (value % 10u));
        value /= 10u;
    }

    while (i > 0u) {
        uart0_putc(buffer[--i]);
    }
}

int main(void)
{
    uint32_t counter = 0u;

    systick_init_1ms();
    uart0_init_115200();

    while (1) {
        uart0_puts("TM4C C test ");
        uart0_put_dec_u32(counter);
        uart0_puts("\r\n");
        counter++;
        delay_ms(1000u);
    }
}
