#include "lpc111x_min.h"
#include "clock.h"
#include "systick.h"
#include "uart.h"

/*
 * power_floor project
 *
 * Goal:
 *   Provide a "best-effort" minimum-current deep-sleep test image for LPC1114/102.
 *
 * Measurement intent:
 *   - Enter deep-sleep (SLEEPDEEP=1) and remain there indefinitely.
 *   - Do not keep watchdog/timer wake infrastructure running.
 *   - Shut down analog/oscillator blocks in deep-sleep as documented.
 *   - Put attached external interfaces into benign static states.
 *
 * Datasheet references used in this implementation:
 *   - datasheets/LPC1114/LPC111X.pdf, Table 16 (deep-sleep current test conditions)
 *   - datasheets/LPC1114/LPC111X.pdf, Fig. 26 note: BOD disabled; analog blocks/oscillators disabled
 *   - datasheets/LPC1114/UM10398.pdf power-management and deep-sleep entry sequence
 */

#define BOOT_ANNOUNCE_MS 5000u

/* SYSAHBCLKCTRL bit positions used in this file (UM10398). */
#define AHBCLK_GPIO_BIT      6u
#define AHBCLK_CT16B0_BIT    7u
#define AHBCLK_CT16B1_BIT    8u
#define AHBCLK_CT32B0_BIT    9u
#define AHBCLK_CT32B1_BIT   10u
#define AHBCLK_SSP0_BIT     11u
#define AHBCLK_UART_BIT     12u
#define AHBCLK_ADC_BIT      13u
#define AHBCLK_WDT_BIT      15u

/* PDRUNCFG / PDSLEEPCFG bits (UM10398). */
#define PD_SYSOSC_BIT        5u
#define PD_WDTOSC_BIT        6u
#define PD_SYSPLL_BIT        7u
#define PD_ADC_BIT          10u
#define PD_BOD_BIT          11u

static void delay_ms(uint32_t ms)
{
    uint32_t start = systick_millis();
    while ((uint32_t)(systick_millis() - start) < ms) {
        /* Busy wait intentionally: short boot-only delay for human-visible UART text. */
    }
}

static void uart_wait_tx_idle(void)
{
    /*
     * Wait until UART TX shift register is empty before disabling UART clocks.
     * LSR bit 5: THRE (THR empty), bit 6: TEMT (transmitter empty).
     */
    while ((LPC_UART_LSR & (1u << 5)) == 0u) {
        /* wait */
    }
    while ((LPC_UART_LSR & (1u << 6)) == 0u) {
        /* wait */
    }
}

static void iocon_set_gpio_no_pull(volatile uint32_t *reg)
{
    /*
     * IOCON common fields on LPC111x:
     * - FUNC  [2:0] : 0 selects GPIO function (where available)
     * - MODE  [4:3] : 00 inactive (no pull-up / no pull-down)
     * - OD    [10]  : open-drain disable when 0
     */
    *reg &= ~0x7u;           /* FUNC = 0 (GPIO). */
    *reg &= ~(0x3u << 3);    /* MODE = inactive. */
    *reg &= ~(1u << 10);     /* Open-drain disabled. */
}

static void configure_external_pins_for_low_leakage(void)
{
    /*
     * External 23LC1024 SRAM wiring:
     *   PIO0_2 = CS, PIO0_6 = SCK, PIO0_8 = SO (MISO), PIO0_9 = SI (MOSI)
     *
     * Strategy:
     *   - Force pins to GPIO function to avoid unintended peripheral toggling.
     *   - Drive CS high so SRAM is deselected.
     *   - Drive SCK/MOSI low to avoid switching.
     *   - Keep MISO as input (it is driven by SRAM when selected; otherwise high-Z).
     */

    /*
     * Keep SWD debug pins untouched so the part remains easy to recover:
     * - SWDIO/SWCLK are not modified here.
     */

    /* Park all currently defined non-essential pins in benign GPIO mode. */
    iocon_set_gpio_no_pull(&LPC_IOCON_PIO0_1);
    iocon_set_gpio_no_pull(&LPC_IOCON_PIO0_2);
    iocon_set_gpio_no_pull(&LPC_IOCON_PIO0_6);
    iocon_set_gpio_no_pull(&LPC_IOCON_PIO0_8);
    iocon_set_gpio_no_pull(&LPC_IOCON_PIO0_9);
    iocon_set_gpio_no_pull(&LPC_IOCON_PIO1_0);
    iocon_set_gpio_no_pull(&LPC_IOCON_PIO1_2);
    iocon_set_gpio_no_pull(&LPC_IOCON_PIO1_6);
    iocon_set_gpio_no_pull(&LPC_IOCON_PIO1_7);

    /*
     * Port 0 parking:
     * - PIO0_2 (SRAM CS) as output HIGH (deselect)
     * - PIO0_6 (SRAM SCK) as output LOW
     * - PIO0_9 (SRAM SI)  as output LOW
     * - PIO0_8 (SRAM SO)  as input
     * - PIO0_1 as input (unused in this test)
     */
    LPC_GPIO0_DIR |= (1u << 2) | (1u << 6) | (1u << 9);
    LPC_GPIO0_DIR &= ~((1u << 1) | (1u << 8));

    LPC_GPIO0_DATA |= (1u << 2);                 /* CS high (deselect SRAM). */
    LPC_GPIO0_DATA &= ~((1u << 6) | (1u << 9)); /* SCK/SI low. */

    /*
     * Port 1 parking:
     * - PIO1_2 LED output LOW to avoid LED current.
     * - PIO1_0, PIO1_6, PIO1_7 as inputs.
     *
     * Rationale:
     * Driving UART pins against an attached probe can increase current if the
     * external side idles high. Inputs avoid this contention current.
     */
    LPC_GPIO1_DIR |= (1u << 2);
    LPC_GPIO1_DIR &= ~((1u << 0) | (1u << 6) | (1u << 7));
    LPC_GPIO1_DATA &= ~(1u << 2);
}

static void disable_nonessential_ahb_clocks(void)
{
    /*
     * Keep only clocks needed during setup; then disable active peripheral clocks
     * before entering deep-sleep.
     *
     * This removes dynamic current from peripherals and mirrors datasheet intent
     * for low-power characterization.
     */
    LPC_SYSCON_SYSAHBCLKCTRL &= ~(
        (1u << AHBCLK_CT16B0_BIT) |
        (1u << AHBCLK_CT16B1_BIT) |
        (1u << AHBCLK_CT32B0_BIT) |
        (1u << AHBCLK_CT32B1_BIT) |
        (1u << AHBCLK_SSP0_BIT) |
        (1u << AHBCLK_UART_BIT) |
        (1u << AHBCLK_ADC_BIT) |
        (1u << AHBCLK_WDT_BIT));

    /* GPIO clock is no longer needed once output states are latched. */
    LPC_SYSCON_SYSAHBCLKCTRL &= ~(1u << AHBCLK_GPIO_BIT);
}

static void configure_deep_sleep_power_domains(void)
{
    /*
     * Deep-sleep target condition from datasheet characterization:
     *   - BOD disabled
     *   - Oscillators/analog blocks disabled in PDSLEEPCFG
     *
     * PDSLEEPCFG bit semantics:
     *   1 = power-down block in deep-sleep
     *   0 = keep block powered in deep-sleep
     */

    /*
     * Use datasheet characterization setting for minimum deep-sleep current:
     * PDSLEEPCFG = 0x000018FF
     * (BOD disabled; oscillators/analog blocks disabled in deep-sleep).
     */
    LPC_SYSCON_PDSLEEPCFG = 0x000018FFu;

    /* Restore normal run-time power defaults immediately after wake (if any wake occurs). */
    LPC_SYSCON_PDAWAKECFG = LPC_SYSCON_PDRUNCFG;
}

static void disable_start_logic_sources(void)
{
    /*
     * This project is for floor-current measurement, so disable programmable
     * start-logic wake sources. External reset/SWD can still recover the part.
     */
    LPC_SYSCON_STARTERP0 = 0u;
    LPC_SYSCON_STARTRSRP0CLR = 0x0FFFu;
}

int main(void)
{
    /*
     * Bring up clock/UART only to announce mode and provide a deterministic
     * window to start current capture.
     */
    clock_init_48mhz();
    systick_init_1ms();
    uart_init_57600();

    uart_puts("POWER_FLOOR: prepare deep-sleep floor measurement\r\n");
    uart_puts("POWER_FLOOR: entering deep-sleep in 5s\r\n");
    delay_ms(BOOT_ANNOUNCE_MS);

    /* Ensure message has physically left TX before we gate UART clock. */
    uart_wait_tx_idle();

    /*
     * Stop SysTick before deep-sleep entry. Leaving SysTick running can
     * continuously wake the core and inflate measured current.
     */
    SYST_CSR = 0u;

    /*
     * 1) Drive external interface pins into static, low-leakage states.
     * 2) Remove peripheral clocks that are not required for deep-sleep entry.
     * 3) Configure deep-sleep power domain shutdown.
     * 4) Disable programmed start-logic wake sources.
     */
    configure_external_pins_for_low_leakage();
    disable_nonessential_ahb_clocks();
    configure_deep_sleep_power_domains();
    disable_start_logic_sources();

    /*
     * Ensure deep power-down mode is not selected accidentally.
     * PCON bit 1 controls deep power-down request path.
     */
    LPC_PMU_PCON &= ~(1u << 1);

    /*
     * Enter deep-sleep and remain in WFI loop.
     * Disable interrupts to avoid accidental wake from stray enabled IRQs.
     */
    __asm__ volatile ("cpsid i");
    SCB_SCR |= (1u << 2); /* SLEEPDEEP = 1 */
    while (1) {
        __asm__ volatile ("wfi");
    }
}
