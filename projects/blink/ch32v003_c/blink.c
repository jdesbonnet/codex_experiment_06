#include "ch32fun.h"

/*
 * CH32V003 blink smoke test.
 * Pin choice follows a common CH32V003 eval-board LED mapping (PD0).
 * If your board routes LED differently, update LED_PIN.
 */
#define LED_PIN PD4

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
