#include <stdint.h>

#include "tm4c123gh6pm.h"

/*
 * TM4C123GXL LaunchPad blink test.
 *
 * Board-specific note:
 *   The LaunchPad RGB user LED is wired to Port F. This test uses PF1
 *   (the red LED channel) so it does not depend on any external wiring.
 *
 * Clocking note:
 *   This code keeps the MCU on its reset clock configuration and assumes the
 *   default 16 MHz precision internal oscillator when programming SysTick for
 *   a 1 ms tick.
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

static void systick_init_1ms(void)
{
    /*
     * SysTick reload value for 1 ms at the default 16 MHz internal oscillator:
     * 16,000 cycles - 1 because the counter includes zero.
     */
    NVIC_ST_RELOAD_R = 16000u - 1u;
    NVIC_ST_CURRENT_R = 0u;
    NVIC_ST_CTRL_R = NVIC_ST_CTRL_CLK_SRC | NVIC_ST_CTRL_INTEN | NVIC_ST_CTRL_ENABLE;
}

static void gpiof_red_led_init(void)
{
    SYSCTL_RCGCGPIO_R |= (1u << TM4C123_PORTF_BIT);
    while ((SYSCTL_PRGPIO_R & (1u << TM4C123_PORTF_BIT)) == 0u) {
        /* Wait until Port F leaves reset before touching its registers. */
    }

    /*
     * PF1 does not require the PF0 unlock sequence, but setting CR is harmless
     * and keeps the initialization sequence explicit.
     */
    GPIO_PORTF_LOCK_R = 0x4C4F434Bu;
    GPIO_PORTF_CR_R |= TM4C123_PF1_RED_LED;

    GPIO_PORTF_AMSEL_R &= ~TM4C123_PF1_RED_LED;
    GPIO_PORTF_PCTL_R &= ~(0xFu << 4);
    GPIO_PORTF_AFSEL_R &= ~TM4C123_PF1_RED_LED;
    GPIO_PORTF_DIR_R |= TM4C123_PF1_RED_LED;
    GPIO_PORTF_DR2R_R |= TM4C123_PF1_RED_LED;
    GPIO_PORTF_DEN_R |= TM4C123_PF1_RED_LED;
    GPIO_PORTF_DATA_R &= ~TM4C123_PF1_RED_LED;
}

int main(void)
{
    gpiof_red_led_init();
    systick_init_1ms();

    while (1) {
        GPIO_PORTF_DATA_R ^= TM4C123_PF1_RED_LED;
        delay_ms(250u);
    }
}
