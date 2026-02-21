#include "lpc111x_min.h"
#include "clock.h"

void clock_init_48mhz(void)
{
    /* Power up SYSPLL and ensure IRC is powered. Reserved bits per UM10398 Table 44. */
    uint32_t pdruncfg = LPC_SYSCON_PDRUNCFG;
    pdruncfg &= ~((1u << 7) | (1u << 1) | (1u << 0));
    pdruncfg |= (1u << 8) | (1u << 10) | (1u << 11) | (7u << 13);
    pdruncfg &= ~((1u << 9) | (1u << 12));
    LPC_SYSCON_PDRUNCFG = pdruncfg;

    /* Select IRC as PLL source. */
    LPC_SYSCON_SYSPLLCLKSEL = 0x0u;
    LPC_SYSCON_SYSPLLCLKUEN = 0x0u;
    LPC_SYSCON_SYSPLLCLKUEN = 0x1u;

    /* Configure PLL: M = 4 (MSEL=3), P = 2 (PSEL=1). */
    LPC_SYSCON_SYSPLLCTRL = (3u << 0) | (1u << 5);

    /* Wait for PLL lock. */
    while ((LPC_SYSCON_SYSPLLSTAT & 0x1u) == 0u) {
        /* spin */
    }

    /* Set main clock to SYSPLL clock out. */
    LPC_SYSCON_MAINCLKSEL = 0x3u;
    LPC_SYSCON_MAINCLKUEN = 0x0u;
    LPC_SYSCON_MAINCLKUEN = 0x1u;

    /* AHB divider = 1 (system clock = main clock). */
    LPC_SYSCON_SYSAHBCLKDIV = 1u;
}
