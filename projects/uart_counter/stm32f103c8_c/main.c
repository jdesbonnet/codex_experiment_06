#include <stdint.h>

#include "stm32f103xb.h"

/*
 * STM32F103C8 UART counter demo.
 *
 * Wiring assumption:
 *   USART1 is used on the default pins:
 *   - PA9  = USART1_TX
 *   - PA10 = USART1_RX
 *
 * Clocking:
 *   The code keeps the reset clock configuration, so USART1 runs from the
 *   default 8 MHz HSI-derived APB2 clock.
 */

#define UART_BAUD 57600u

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

static void usart1_putc(char ch)
{
    while ((USART1->SR & USART_SR_TXE) == 0u) {
        /* Wait for space in the transmit data register. */
    }
    USART1->DR = (uint16_t)(uint8_t)ch;
}

static void usart1_puts(const char *text)
{
    while (*text != '\0') {
        usart1_putc(*text++);
    }
}

static void usart1_put_dec_u32(uint32_t value)
{
    char buffer[10];
    uint32_t i = 0u;

    if (value == 0u) {
        usart1_putc('0');
        return;
    }

    while (value != 0u) {
        buffer[i++] = (char)('0' + (value % 10u));
        value /= 10u;
    }

    while (i > 0u) {
        usart1_putc(buffer[--i]);
    }
}

static void usart1_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPAEN | RCC_APB2ENR_USART1EN;

    /*
     * PA9 = alternate-function push-pull, 50 MHz output
     * PA10 = floating input
     */
    GPIOA->CRH &= ~(GPIO_CRH_MODE9 | GPIO_CRH_CNF9 | GPIO_CRH_MODE10 | GPIO_CRH_CNF10);
    GPIOA->CRH |= GPIO_CRH_MODE9 | GPIO_CRH_CNF9_1 | GPIO_CRH_CNF10_0;

    USART1->CR1 = 0u;
    USART1->BRR = (SystemCoreClock + (UART_BAUD / 2u)) / UART_BAUD;
    USART1->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

static void usart1_poll_echo(void)
{
    while ((USART1->SR & USART_SR_RXNE) != 0u) {
        uint8_t ch = (uint8_t)USART1->DR;
        usart1_putc((char)ch);
    }
}

int main(void)
{
    uint32_t counter = 0u;

    SystemCoreClockUpdate();
    SysTick_Config(SystemCoreClock / 1000u);
    usart1_init();

    usart1_puts("STM32 C USART1 PA9/PA10 57600 8N1\r\n");
    usart1_puts("Type text to test RX/TX echo.\r\n");

    while (1) {
        usart1_puts("STM32 C test ");
        usart1_put_dec_u32(counter);
        usart1_puts("\r\n");
        counter++;

        for (uint32_t elapsed = 0u; elapsed < 1000u; elapsed += 10u) {
            usart1_poll_echo();
            delay_ms(10u);
        }
    }
}
