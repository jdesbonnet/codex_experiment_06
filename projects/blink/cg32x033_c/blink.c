#include "ch32fun.h"

/*
 * CG32X033 blink smoke test.
 * The attached board's LED routing has not been validated yet; override
 * LED_PIN from the Makefile if needed.
 */
#ifndef LED_PIN
#define LED_PIN PC0
#endif

int main(void)
{
	SystemInit();
	funGpioInitAll();

	funPinMode(LED_PIN, GPIO_Speed_10MHz | GPIO_CNF_OUT_PP);

	while (1) {
		funDigitalWrite(LED_PIN, FUN_HIGH);
		Delay_Ms(250);
		funDigitalWrite(LED_PIN, FUN_LOW);
		Delay_Ms(250);
	}
}
