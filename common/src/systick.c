#include "lpc111x_min.h"
#include "systick.h"

static volatile uint32_t g_ms = 0u;

void SysTick_Handler(void)
{
    g_ms++;
}

void systick_init_1ms(void)
{
    /* 48 MHz system clock -> 1 ms tick. */
    SYST_RVR = 48000u - 1u;
    SYST_CVR = 0u;
    /* ENABLE | TICKINT | CLKSOURCE (processor clock). */
    SYST_CSR = (1u << 0) | (1u << 1) | (1u << 2);
}

uint32_t systick_millis(void)
{
    return g_ms;
}
