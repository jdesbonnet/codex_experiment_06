#include "ch32fun.h"
#include "tiny_vm.h"

#include <stdint.h>
#include <stdio.h>

#define LED_PIN PD4
#define TINY_VM_ACTIVITY_LED 1u

#define VM_UPLOAD_MAGIC0 'T'
#define VM_UPLOAD_MAGIC1 'V'
#define VM_UPLOAD_MAGIC2 'M'
#define VM_UPLOAD_MAGIC3 '1'

#define BOOT_UPLOAD_WINDOW_MS 15000u
#define BYTE_TIMEOUT_MS 250u
#define WAIT_FOREVER_MS 0xFFFFFFFFu

enum {
	HOST_LED_WRITE = 0,
	HOST_DELAY_MS = 1,
	HOST_UART_PRINTLN_U32 = 2,
	HOST_UART_PRINTLN_HEX32 = 3
};

static void uart_init_57600_rx_tx(void)
{
	const uint32_t brr = (FUNCONF_SYSTEM_CORE_CLOCK + 28800u) / 57600u;
	RCC->APB2PCENR |= RCC_APB2Periph_GPIOD | RCC_APB2Periph_USART1;

	/* PD5 TX AF push-pull, PD6 RX floating input. */
	GPIOD->CFGLR &= ~(0xFu << (4u * 5u));
	GPIOD->CFGLR |= (uint32_t)(GPIO_Speed_10MHz | GPIO_CNF_OUT_PP_AF) << (4u * 5u);
	GPIOD->CFGLR &= ~(0xFu << (4u * 6u));
	GPIOD->CFGLR |= (uint32_t)GPIO_CNF_IN_FLOATING << (4u * 6u);

	USART1->CTLR1 = USART_WordLength_8b | USART_Parity_No | USART_Mode_Tx | USART_Mode_Rx;
	USART1->CTLR2 = USART_StopBits_1;
	USART1->CTLR3 = USART_HardwareFlowControl_None;
	USART1->BRR = brr;
	USART1->CTLR1 |= CTLR1_UE_Set;
}

static int uart_read_byte_timeout(uint8_t *out, uint32_t timeout_ms)
{
	while (1) {
		if ((USART1->STATR & USART_FLAG_RXNE) != 0u) {
			*out = (uint8_t)(USART1->DATAR & 0xFFu);
			return 1;
		}
		if (timeout_ms != WAIT_FOREVER_MS) {
			if (timeout_ms == 0u) {
				return 0;
			}
			timeout_ms--;
		}
		Delay_Ms(1);
	}
}

static int wait_magic_start(uint32_t timeout_ms)
{
	uint8_t b = 0;
	while (1) {
		if (timeout_ms != WAIT_FOREVER_MS) {
			if (timeout_ms == 0u) {
				return 0;
			}
			timeout_ms--;
		}
		if (!uart_read_byte_timeout(&b, 1u)) {
			continue;
		}
		if (b == (uint8_t)VM_UPLOAD_MAGIC0) {
			return 1;
		}
	}
}

static int vm_receive_program(tiny_vm_t *vm, uint32_t first_byte_timeout_ms)
{
	uint8_t b = 0;
	uint8_t lo = 0;
	uint8_t hi = 0;
	uint16_t len = 0;
	uint16_t i = 0;
	uint8_t checksum = 0;
	uint8_t expected = 0;

	if (!wait_magic_start(first_byte_timeout_ms)) {
		return 0;
	}
	if (!uart_read_byte_timeout(&b, BYTE_TIMEOUT_MS) || b != (uint8_t)VM_UPLOAD_MAGIC1) {
		return -1;
	}
	if (!uart_read_byte_timeout(&b, BYTE_TIMEOUT_MS) || b != (uint8_t)VM_UPLOAD_MAGIC2) {
		return -1;
	}
	if (!uart_read_byte_timeout(&b, BYTE_TIMEOUT_MS) || b != (uint8_t)VM_UPLOAD_MAGIC3) {
		return -1;
	}
	if (!uart_read_byte_timeout(&lo, BYTE_TIMEOUT_MS)) {
		return -1;
	}
	if (!uart_read_byte_timeout(&hi, BYTE_TIMEOUT_MS)) {
		return -1;
	}
	len = (uint16_t)(((uint16_t)hi << 8) | lo);
	if (len == 0u || len > TINY_VM_CODE_MAX) {
		return -1;
	}
	for (i = 0u; i < len; i++) {
		if (!uart_read_byte_timeout(&b, BYTE_TIMEOUT_MS)) {
			return -1;
		}
		vm->code[i] = b;
		checksum = (uint8_t)(checksum + b);
	}
	if (!uart_read_byte_timeout(&expected, BYTE_TIMEOUT_MS)) {
		return -1;
	}
	if (checksum != expected) {
		return -1;
	}
	return tiny_vm_load(vm, vm->code, len);
}

static int vm_host_call(tiny_vm_t *vm, uint8_t id, void *ctx)
{
	int32_t v = 0;
	(void)ctx;

	switch (id) {
	case HOST_LED_WRITE:
		if (tiny_vm_pop(vm, &v) < 0) {
			return -1;
		}
		/* Eval board LED on PD4 is active-low. */
		funDigitalWrite(LED_PIN, v ? FUN_LOW : FUN_HIGH);
		return 0;
	case HOST_DELAY_MS:
		if (tiny_vm_pop(vm, &v) < 0) {
			return -1;
		}
		if (v < 0) {
			v = 0;
		}
		Delay_Ms((uint32_t)v);
		return 0;
	case HOST_UART_PRINTLN_U32:
		if (tiny_vm_pop(vm, &v) < 0) {
			return -1;
		}
		printf("%ld\r\n", (long)v);
		return 0;
	case HOST_UART_PRINTLN_HEX32:
		if (tiny_vm_pop(vm, &v) < 0) {
			return -1;
		}
		printf("%08lX\r\n", (unsigned long)(uint32_t)v);
		return 0;
	default:
		return -1;
	}
}

#if TINY_VM_ACTIVITY_LED
static void vm_trace_led_hook(tiny_vm_t *vm, uint8_t op, void *ctx)
{
	static uint8_t led_on = 0u;
	(void)vm;
	(void)op;
	(void)ctx;
	led_on = (uint8_t)!led_on;
	/* Eval board LED on PD4 is active-low. */
	funDigitalWrite(LED_PIN, led_on ? FUN_LOW : FUN_HIGH);
}
#endif

int main(void)
{
	tiny_vm_t vm;
	int rc;

	SystemInit();
	uart_init_57600_rx_tx();
	funGpioInitAll();
	funPinMode(LED_PIN, GPIO_Speed_10MHz | GPIO_CNF_OUT_PP);
	funDigitalWrite(LED_PIN, FUN_HIGH);

	tiny_vm_init(&vm, vm_host_call, 0);
#if TINY_VM_ACTIVITY_LED
	tiny_vm_set_trace_hook(&vm, vm_trace_led_hook, 0);
#endif

	printf("tiny_vm: upload frame TVM1+len+code+sum\r\n");
	printf("tiny_vm: boot window 15s\r\n");

	rc = vm_receive_program(&vm, BOOT_UPLOAD_WINDOW_MS);
	if (rc < 0) {
		printf("tiny_vm: boot upload failed\r\n");
	} else {
		printf("tiny_vm: image loaded\r\n");
	}

	while (1) {
		if (vm.code_len == 0u) {
			rc = vm_receive_program(&vm, WAIT_FOREVER_MS);
			if (rc > 0) {
				printf("tiny_vm: image loaded\r\n");
			} else {
				printf("tiny_vm: upload failed\r\n");
				continue;
			}
		}

		rc = tiny_vm_exec(&vm, 128u);
		if (rc == TINY_VM_STEP_LIMIT) {
			continue;
		}
		if (rc == TINY_VM_HALT) {
			printf("tiny_vm: halt\r\n");
		} else if (rc < 0) {
			printf("tiny_vm: runtime error\r\n");
		}
		vm.code_len = 0u;
	}
}
