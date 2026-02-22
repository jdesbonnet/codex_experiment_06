#include "lpc111x_min.h"
#include "clock.h"
#include "systick.h"
#include "uart.h"

#define WDT_OSC_FREQ_HZ   600000u
#define WDT_OSC_DIVSEL    31u
#define WDT_CLKSEL_WDTOSC 2u
static volatile uint32_t g_wake = 0u;

void WAKEUP_IRQHandler(void)
{
    /* Clear start logic status for PIO0_1 and mark wake. */
    LPC_SYSCON_STARTRSRP0CLR = (1u << 1);
    g_wake = 1u;
}

static void wdt_clock_init(void)
{
    /* Switch main clock to WDT output. */
    LPC_SYSCON_MAINCLKSEL = WDT_CLKSEL_WDTOSC;
    LPC_SYSCON_MAINCLKUEN = 0u;
    LPC_SYSCON_MAINCLKUEN = 1u;
    LPC_SYSCON_MAINCLKUEN = 0u;
    LPC_SYSCON_MAINCLKUEN = 1u;
    while ((LPC_SYSCON_MAINCLKUEN & 0x1u) == 0u) {
        /* wait */
    }
}

static void timer_wake_init_10s(void)
{
    /* Power up WDT oscillator and keep reserved bits as required. */
    uint32_t pdrun = LPC_SYSCON_PDRUNCFG;
    pdrun &= ~(1u << 6); /* WDTOSC_PD = 0 (powered). */
    pdrun |= (1u << 8) | (1u << 10) | (1u << 11) | (7u << 13);
    pdrun &= ~((1u << 9) | (1u << 12));
    LPC_SYSCON_PDRUNCFG = pdrun;

    /* Deep-sleep config: WDT osc on, BOD off (matches reference). */
    LPC_SYSCON_PDSLEEPCFG = 0x000018BFu;

    /* Configure WDT oscillator: FREQSEL=1 (0.6 MHz), DIVSEL=31 (divide by 64). */
    LPC_SYSCON_WDTOSCCTRL = (1u << 5) | WDT_OSC_DIVSEL;

    /* Restore power configuration after wake-up. */
    LPC_SYSCON_PDAWAKECFG = LPC_SYSCON_PDRUNCFG;

    /* Enable the clock for CT32B0 (in case it's not enabled). */
    LPC_SYSCON_SYSAHBCLKCTRL |= (1u << 9);

    /* Configure 0.1 as CT32B0_MAT2, no pull-up. */
    LPC_IOCON_PIO0_1 &= ~0x7u;
    LPC_IOCON_PIO0_1 |= 0x2u;
    LPC_IOCON_PIO0_1 &= ~((0x3u << 3) | (1u << 10));

    /* Timer setup for ~10s using WDT oscillator as main clock. */
    uint32_t clk_hz = WDT_OSC_FREQ_HZ / (2u * (1u + WDT_OSC_DIVSEL));
    uint32_t ticks = clk_hz * 10u;

    LPC_CT32B0_TCR = 0x02u; /* reset */
    LPC_CT32B0_PR = 0u;
    LPC_CT32B0_TC = 0u;
    LPC_CT32B0_MR0 = 0u;
    LPC_CT32B0_MR2 = ticks;
    /* MR2 reset on match. */
    LPC_CT32B0_MCR = (1u << 7);
    LPC_CT32B0_IR = 0xFFu;
    /* Set MAT2 high on match. */
    LPC_CT32B0_EMR &= ~(0xFFu << 4);
    LPC_CT32B0_EMR |= (0x2u << 8);

    /* Enable wakeup interrupt for PIO0_1 (IRQ1). */
    LPC_SYSCON_STARTAPRP0 |= (1u << 1);
    LPC_SYSCON_STARTRSRP0CLR = 0x0FFFu;
    LPC_SYSCON_STARTERP0 |= (1u << 1);
    NVIC_ICPR0 = (1u << 1);
    NVIC_ISER0 = (1u << 1);

    /* Switch to WDTOSC and start timer. */
    wdt_clock_init();
    LPC_CT32B0_TCR = 0x01u; /* enable */
}

static void delay_ms(uint32_t ms)
{
    uint32_t start = systick_millis();
    while ((uint32_t)(systick_millis() - start) < ms) {
        /* spin */
    }
}

int main(void)
{
    clock_init_48mhz();
    systick_init_1ms();
    uart_init_57600();

    /* Boot diagnostics. */
    uart_puts("Boot: WDMOD=0x");
    uart_put_hex8((uint8_t)((LPC_WDT_WDMOD >> 24) & 0xFFu));
    uart_put_hex8((uint8_t)((LPC_WDT_WDMOD >> 16) & 0xFFu));
    uart_put_hex8((uint8_t)((LPC_WDT_WDMOD >> 8) & 0xFFu));
    uart_put_hex8((uint8_t)(LPC_WDT_WDMOD & 0xFFu));
    uart_puts(" SYSRSTSTAT=0x");
    uart_put_hex8((uint8_t)((LPC_SYSCON_SYSRSTSTAT >> 24) & 0xFFu));
    uart_put_hex8((uint8_t)((LPC_SYSCON_SYSRSTSTAT >> 16) & 0xFFu));
    uart_put_hex8((uint8_t)((LPC_SYSCON_SYSRSTSTAT >> 8) & 0xFFu));
    uart_put_hex8((uint8_t)(LPC_SYSCON_SYSRSTSTAT & 0xFFu));
    uart_puts(" STARTSRP0=0x");
    uart_put_hex8((uint8_t)((LPC_SYSCON_STARTSRP0 >> 24) & 0xFFu));
    uart_put_hex8((uint8_t)((LPC_SYSCON_STARTSRP0 >> 16) & 0xFFu));
    uart_put_hex8((uint8_t)((LPC_SYSCON_STARTSRP0 >> 8) & 0xFFu));
    uart_put_hex8((uint8_t)(LPC_SYSCON_STARTSRP0 & 0xFFu));
    uart_puts(" GPREG0=0x");
    uart_put_hex8((uint8_t)((LPC_PMU_GPREG0 >> 24) & 0xFFu));
    uart_put_hex8((uint8_t)((LPC_PMU_GPREG0 >> 16) & 0xFFu));
    uart_put_hex8((uint8_t)((LPC_PMU_GPREG0 >> 8) & 0xFFu));
    uart_put_hex8((uint8_t)(LPC_PMU_GPREG0 & 0xFFu));
    uart_puts("\r\n");

    /* Clear latched reset reasons (write 1s to clear). */
    LPC_SYSCON_SYSRSTSTAT = 0x1Fu;

    if (g_wake != 0u) {
        g_wake = 0u;
        uart_puts("Sleep: awake again\r\n");
    }

    uart_puts("Sleep: starting in 10s...\r\n");
    delay_ms(10000u);

    while (1) {
        uart_puts("Sleep: entering deep-sleep for ~10s\r\n\r\n");
        g_wake = 0u;

        /* Prepare for deep-sleep wake via CT32B0 match interrupt. */
        timer_wake_init_10s();

        /* Ensure deep power-down is disabled. */
        LPC_PMU_PCON &= ~(1u << 1);

        /* Enter deep-sleep. */
        SCB_SCR |= (1u << 2); /* SLEEPDEEP */
        while (g_wake == 0u) {
            __asm__ volatile ("wfi");
        }
        SCB_SCR &= ~(1u << 2);

        /* Restore normal clocks after wake. */
        clock_init_48mhz();
        systick_init_1ms();
        uart_init_57600();

        uart_puts("Sleep: awake again\r\n");
        delay_ms(5000u);
    }
}
