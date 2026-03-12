#include <stdbool.h>
#include <stdint.h>

#include "stm32f103xb.h"

/*
 * Common STM32F103C8 "Blue Pill" boards wire the user LED to PC13 and the LED
 * is active-low. This blink test uses the default reset clocking, which leaves
 * the MCU running from the internal 8 MHz HSI oscillator.
 */

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

static void gpio_pc13_led_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_IOPCEN;

    /*
     * PC13 uses GPIOC_CRH bits [23:20]:
     *   MODE13 = 0b10 => output, max 2 MHz
     *   CNF13  = 0b00 => general purpose push-pull
     */
    GPIOC->CRH &= ~(GPIO_CRH_MODE13 | GPIO_CRH_CNF13);
    GPIOC->CRH |= GPIO_CRH_MODE13_1;

    /* Active-low LED off by default. */
    GPIOC->BSRR = GPIO_BSRR_BS13;
}

int main(void)
{
    bool led_on = false;

    SystemCoreClockUpdate();
    gpio_pc13_led_init();
    SysTick_Config(SystemCoreClock / 1000U);

    while (1) {
        if (led_on) {
            GPIOC->BSRR = GPIO_BSRR_BS13;
        } else {
            GPIOC->BRR = GPIO_BRR_BR13;
        }
        led_on = !led_on;
        delay_ms(250U);
    }
}
