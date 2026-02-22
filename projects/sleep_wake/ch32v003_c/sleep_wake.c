#include "ch32fun.h"
#include <stdio.h>

/*
 * sleep_wake (CH32V003)
 *
 * Loop behavior:
 * - announce "SLEEP"
 * - enter standby and wake via internal AWU timer (~5 s)
 * - reinitialize clocking after wake
 * - announce "AWAKE"
 * - stay awake for 5 s
 *
 * Reference timing (from ch32fun standby example):
 *   t = AWUWR / (fLSI / AWUPSC), with fLSI ~= 128 kHz.
 */

#define BOOT_DELAY_MS   10000u
#define AWAKE_DELAY_MS   5000u
/* Match the CH32 blink project LED pin. */
#define LED_PIN          4u

/* ~5.04 s with AWUPSC=10240 and AWUWR=63. */
#define AWU_PRESCALER   PWR_AWU_Prescaler_10240
#define AWU_WINDOW      63u

static void led_init_output(void)
{
	RCC->APB2PCENR |= RCC_APB2Periph_GPIOD;
	GPIOD->CFGLR &= ~(0xFu << (4u * LED_PIN));
	GPIOD->CFGLR |= ((GPIO_CNF_OUT_PP | GPIO_Speed_30MHz) << (4u * LED_PIN));
}

static void led_set(int on)
{
	if (on) {
		/* Eval-board LED on PD4 is active-low (sink current to turn on). */
		GPIOD->BSHR = (1u << (LED_PIN + 16u));
	} else {
		GPIOD->BSHR = (1u << LED_PIN);
	}
}

static void prepare_gpio_for_sleep(void)
{
	/*
	 * Avoid floating inputs: configure all GPIOs except PD1 (SWD) as
	 * input with pull-down so standby current is stable and recoverable.
	 */
	RCC->APB2PCENR |= RCC_APB2Periph_GPIOA | RCC_APB2Periph_GPIOC | RCC_APB2Periph_GPIOD;

	GPIOA->CFGLR = (GPIO_CNF_IN_PUPD << (4 * 1)) |
		       (GPIO_CNF_IN_PUPD << (4 * 2));
	GPIOA->BSHR = GPIO_BSHR_BR1 | GPIO_BSHR_BR2;

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

	/* Leave PD4 out of the blanket input config; keep it as a driven LED pin. */
	GPIOD->CFGLR = (GPIO_CNF_IN_PUPD << (4 * 0)) |
		       (GPIO_CNF_IN_PUPD << (4 * 2)) |
		       (GPIO_CNF_IN_PUPD << (4 * 3)) |
		       (GPIO_CNF_IN_PUPD << (4 * 5)) |
		       (GPIO_CNF_IN_PUPD << (4 * 6)) |
		       (GPIO_CNF_IN_PUPD << (4 * 7));
	GPIOD->BSHR = GPIO_BSHR_BR0 | GPIO_BSHR_BR2 | GPIO_BSHR_BR3 |
		      GPIO_BSHR_BR5 | GPIO_BSHR_BR6 | GPIO_BSHR_BR7;

	/* Keep LED off in sleep as a strong output (active-low LED on PD4). */
	led_init_output();
	led_set(0);
}

static void configure_awu_for_sleep(void)
{
	/* Enable PWR clock and LSI required by AWU. */
	RCC->APB1PCENR |= RCC_APB1Periph_PWR;
	RCC->RSTSCKR |= RCC_LSION;
	while ((RCC->RSTSCKR & RCC_LSIRDY) == 0u) {
	}

	/* AWU wake event is mapped on EXTI line 9. */
	EXTI->EVENR |= EXTI_Line9;
	EXTI->FTENR |= EXTI_Line9;

	PWR->AWUPSC = AWU_PRESCALER;
	PWR->AWUWR = AWU_WINDOW;
	PWR->AWUCSR |= (1u << 1); /* AWU enable */
}

int main(void)
{
	SystemInit();
	Delay_Ms(BOOT_DELAY_MS);

	printf("sleep_wake ch32v003\r\n");

	prepare_gpio_for_sleep();
	configure_awu_for_sleep();

	for (;;) {
		led_set(0);
		printf("SLEEP\r\n");
		Delay_Ms(20);

		/* Enter standby and wait for AWU wake event. */
		PWR->CTLR |= PWR_CTLR_PDDS;
		PFIC->SCTLR |= (1u << 2); /* SLEEPDEEP */
		__WFE();

		/* Wake path: restore system clocks/peripherals for active phase. */
		SystemInit();
		led_init_output();
		led_set(1);
		printf("AWAKE\r\n");
		Delay_Ms(AWAKE_DELAY_MS);
		prepare_gpio_for_sleep();
	}
}
