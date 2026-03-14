#include <stdbool.h>
#include <stdint.h>

#include "fsl_device_registers.h"

#ifndef LPC824_BLINK_PIN
#define LPC824_BLINK_PIN 12u
#endif

#ifndef LPC824_BLINK_ACTIVE_LOW
#define LPC824_BLINK_ACTIVE_LOW 1
#endif

volatile uint32_t g_blink_toggle_count;
static volatile uint32_t g_ms_ticks;

void SysTick_Handler(void)
{
    ++g_ms_ticks;
}

static void delay_ms(uint32_t delay)
{
    const uint32_t deadline = g_ms_ticks + delay;

    while ((int32_t)(g_ms_ticks - deadline) < 0) {
    }
}

static inline uint32_t blink_mask(void)
{
    return 1u << LPC824_BLINK_PIN;
}

static void led_write(bool on)
{
#if LPC824_BLINK_ACTIVE_LOW
    if (on) {
        GPIO->CLR[0] = blink_mask();
    } else {
        GPIO->SET[0] = blink_mask();
    }
#else
    if (on) {
        GPIO->SET[0] = blink_mask();
    } else {
        GPIO->CLR[0] = blink_mask();
    }
#endif
}

int main(void)
{
    SYSCON->SYSAHBCLKCTRL |= SYSCON_SYSAHBCLKCTRL_GPIO_MASK;
    GPIO->DIR[0] |= blink_mask();

    led_write(false);

    SystemCoreClockUpdate();
    if (SysTick_Config(SystemCoreClock / 1000u) != 0u) {
        while (1) {
        }
    }

    while (1) {
        led_write(true);
        delay_ms(50u);
        ++g_blink_toggle_count;

        led_write(false);
        delay_ms(50u);
        ++g_blink_toggle_count;
    }
}
