#include "ch32fun.h"

/*
 * power_floor (CH32V003)
 *
 * Goal:
 *   Enter the lowest practical standby state for floor-current measurements.
 *
 * Notes:
 *   - A boot delay is intentional so reflash can happen before deep sleep.
 *   - No wake source is configured; recovery is by reset/power-cycle/reflash flow.
 */

#define BOOT_DELAY_MS 5000u

static void configure_gpio_for_low_leakage(void)
{
	/*
	 * Keep SWD pin PD1 untouched so debug access remains recoverable.
	 *
	 * Configure all other GPIOs as input pull-down to avoid floating inputs.
	 * Floating pins can dominate sleep current.
	 */
	RCC->APB2PCENR |= RCC_APB2Periph_GPIOA | RCC_APB2Periph_GPIOC | RCC_APB2Periph_GPIOD;

	/* PA1, PA2 */
	GPIOA->CFGLR = (GPIO_CNF_IN_PUPD << (4 * 1)) |
		       (GPIO_CNF_IN_PUPD << (4 * 2));
	GPIOA->BSHR = GPIO_BSHR_BR1 | GPIO_BSHR_BR2;

	/* PC0..PC7 */
	GPIOC->CFGLR = (GPIO_CNF_IN_PUPD << (4 * 0)) |
		       (GPIO_CNF_IN_PUPD << (4 * 1)) |
		       (GPIO_CNF_IN_PUPD << (4 * 2)) |
		       (GPIO_CNF_IN_PUPD << (4 * 3)) |
		       (GPIO_CNF_IN_PUPD << (4 * 4)) |
		       (GPIO_CNF_IN_PUPD << (4 * 5)) |
		       (GPIO_CNF_IN_PUPD << (4 * 6)) |
		       (GPIO_CNF_IN_PUPD << (4 * 7));
	GPIOC->BSHR = GPIO_BSHR_BR0 | GPIO_BSHR_BR1 | GPIO_BSHR_BR2 | GPIO_BSHR_BR3 |
		      GPIO_BSHR_BR4 | GPIO_BSHR_BR5 | GPIO_BSHR_BR6 | GPIO_BSHR_BR7;

	/* PD0, PD2..PD7 (PD1 deliberately skipped) */
	GPIOD->CFGLR = (GPIO_CNF_IN_PUPD << (4 * 0)) |
		       (GPIO_CNF_IN_PUPD << (4 * 2)) |
		       (GPIO_CNF_IN_PUPD << (4 * 3)) |
		       (GPIO_CNF_IN_PUPD << (4 * 4)) |
		       (GPIO_CNF_IN_PUPD << (4 * 5)) |
		       (GPIO_CNF_IN_PUPD << (4 * 6)) |
		       (GPIO_CNF_IN_PUPD << (4 * 7));
	GPIOD->BSHR = GPIO_BSHR_BR0 | GPIO_BSHR_BR2 | GPIO_BSHR_BR3 | GPIO_BSHR_BR4 |
		      GPIO_BSHR_BR5 | GPIO_BSHR_BR6 | GPIO_BSHR_BR7;
}

int main(void)
{
	SystemInit();

	/* Keep CPU awake briefly so reflashing is easy after reset. */
	Delay_Ms(BOOT_DELAY_MS);

	configure_gpio_for_low_leakage();

	/* Put core into standby on deep-sleep entry. */
	RCC->APB1PCENR |= RCC_APB1Periph_PWR;
	PWR->CTLR |= PWR_CTLR_PDDS;
	PFIC->SCTLR |= (1u << 2); /* SLEEPDEEP */

	for (;;) {
		__WFE();
	}
}
