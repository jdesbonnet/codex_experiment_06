#include <stdint.h>

#include "stm32f103xb.h"
#include "tiny_vm.h"

#define LED_ACTIVE_LOW 1u
#define TINY_VM_ACTIVITY_LED 1u

#define VM_UPLOAD_MAGIC0 'T'
#define VM_UPLOAD_MAGIC1 'V'
#define VM_UPLOAD_MAGIC2 'M'
#define VM_UPLOAD_MAGIC3 '1'

#define BOOT_UPLOAD_WINDOW_MS 15000u
#define BYTE_TIMEOUT_MS 250u
#define WAIT_FOREVER_MS 0xFFFFFFFFu
#define UART_BAUD 57600u

enum {
    HOST_LED_WRITE = 0,
    HOST_DELAY_MS = 1,
    HOST_UART_PRINTLN_U32 = 2,
    HOST_UART_PRINTLN_HEX32 = 3
};

static volatile uint32_t g_ms_ticks;

void SysTick_Handler(void)
{
    g_ms_ticks++;
}

static void delay_ms(uint32_t delay_ms)
{
    uint32_t start = g_ms_ticks;
    while ((uint32_t)(g_ms_ticks - start) < delay_ms) {
        /* Wait for the SysTick timebase to advance. */
    }
}

static void usart1_putc(char ch)
{
    while ((USART1->SR & USART_SR_TXE) == 0u) {
        /* Wait for space in the transmit data register. */
    }
    USART1->DR = (uint16_t)(uint8_t)ch;
}

static void usart1_puts(const char *text)
{
    while (*text != '\0') {
        usart1_putc(*text++);
    }
}

static void usart1_put_hex8(uint8_t value)
{
    static const char hex[] = "0123456789ABCDEF";
    usart1_putc(hex[(value >> 4) & 0x0Fu]);
    usart1_putc(hex[value & 0x0Fu]);
}

static void usart1_put_dec_u32(uint32_t value)
{
    char buffer[10];
    uint32_t i = 0u;

    if (value == 0u) {
        usart1_putc('0');
        return;
    }

    while (value != 0u) {
        buffer[i++] = (char)('0' + (value % 10u));
        value /= 10u;
    }

    while (i > 0u) {
        usart1_putc(buffer[--i]);
    }
}

static void usart1_init_57600(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPAEN | RCC_APB2ENR_USART1EN;

    /*
     * PA9  = alternate-function push-pull, 50 MHz output
     * PA10 = floating input
     */
    GPIOA->CRH &= ~(GPIO_CRH_MODE9 | GPIO_CRH_CNF9 | GPIO_CRH_MODE10 | GPIO_CRH_CNF10);
    GPIOA->CRH |= GPIO_CRH_MODE9 | GPIO_CRH_CNF9_1 | GPIO_CRH_CNF10_0;

    USART1->CR1 = 0u;
    USART1->BRR = (SystemCoreClock + (UART_BAUD / 2u)) / UART_BAUD;
    USART1->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

static void led_write(int on)
{
#if LED_ACTIVE_LOW
    if (on != 0) {
        GPIOC->BRR = GPIO_BRR_BR13;
    } else {
        GPIOC->BSRR = GPIO_BSRR_BS13;
    }
#else
    if (on != 0) {
        GPIOC->BSRR = GPIO_BSRR_BS13;
    } else {
        GPIOC->BRR = GPIO_BRR_BR13;
    }
#endif
}

static void led_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_IOPCEN;

    /*
     * PC13 = general-purpose push-pull output, max 2 MHz.
     * This matches the common Blue Pill user LED wiring.
     */
    GPIOC->CRH &= ~(GPIO_CRH_MODE13 | GPIO_CRH_CNF13);
    GPIOC->CRH |= GPIO_CRH_MODE13_1;

    led_write(0);
}

static void host_delay_ms(uint32_t ms)
{
    delay_ms(ms);
}

static int uart_read_byte_timeout(uint8_t *out, uint32_t timeout_ms)
{
    uint32_t start = g_ms_ticks;
    while (1) {
        if ((USART1->SR & USART_SR_RXNE) != 0u) {
            *out = (uint8_t)(USART1->DR & 0xFFu);
            return 1;
        }
        if (timeout_ms != WAIT_FOREVER_MS) {
            if ((uint32_t)(g_ms_ticks - start) >= timeout_ms) {
                return 0;
            }
        }
    }
}

static int wait_magic_start(uint32_t timeout_ms)
{
    uint8_t b = 0;
    uint32_t start = g_ms_ticks;
    while (1) {
        if (timeout_ms != WAIT_FOREVER_MS) {
            if ((uint32_t)(g_ms_ticks - start) >= timeout_ms) {
                return 0;
            }
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
        led_write(v != 0);
        return 0;
    case HOST_DELAY_MS:
        if (tiny_vm_pop(vm, &v) < 0) {
            return -1;
        }
        if (v < 0) {
            v = 0;
        }
        host_delay_ms((uint32_t)v);
        return 0;
    case HOST_UART_PRINTLN_U32:
        if (tiny_vm_pop(vm, &v) < 0) {
            return -1;
        }
        if (v < 0) {
            usart1_putc('-');
            usart1_put_dec_u32((uint32_t)(-v));
        } else {
            usart1_put_dec_u32((uint32_t)v);
        }
        usart1_puts("\r\n");
        return 0;
    case HOST_UART_PRINTLN_HEX32: {
        uint32_t uv;
        if (tiny_vm_pop(vm, &v) < 0) {
            return -1;
        }
        uv = (uint32_t)v;
        usart1_put_hex8((uint8_t)((uv >> 24) & 0xFFu));
        usart1_put_hex8((uint8_t)((uv >> 16) & 0xFFu));
        usart1_put_hex8((uint8_t)((uv >> 8) & 0xFFu));
        usart1_put_hex8((uint8_t)(uv & 0xFFu));
        usart1_puts("\r\n");
        return 0;
    }
    default:
        return -1;
    }
}

#if TINY_VM_ACTIVITY_LED
static void vm_trace_led_hook(tiny_vm_t *vm, uint8_t op, void *ctx)
{
    (void)vm;
    (void)op;
    (void)ctx;
    static uint32_t divider = 0u;

    divider++;
    if ((divider & 0x03u) == 0u) {
        GPIOC->ODR ^= GPIO_ODR_ODR13;
    }
}
#endif

int main(void)
{
    tiny_vm_t vm;
    int rc;

    SystemCoreClockUpdate();
    SysTick_Config(SystemCoreClock / 1000u);
    usart1_init_57600();
    led_init();

    tiny_vm_init(&vm, vm_host_call, 0);
#if TINY_VM_ACTIVITY_LED
    tiny_vm_set_trace_hook(&vm, vm_trace_led_hook, 0);
#endif

    usart1_puts("tiny_vm: upload frame TVM1+len+code+sum\r\n");
    usart1_puts("tiny_vm: boot window 15s\r\n");

    rc = vm_receive_program(&vm, BOOT_UPLOAD_WINDOW_MS);
    if (rc < 0) {
        usart1_puts("tiny_vm: boot upload failed\r\n");
    } else {
        usart1_puts("tiny_vm: image loaded\r\n");
    }

    while (1) {
        if (vm.code_len == 0u) {
            rc = vm_receive_program(&vm, WAIT_FOREVER_MS);
            if (rc > 0) {
                usart1_puts("tiny_vm: image loaded\r\n");
            } else {
                usart1_puts("tiny_vm: upload failed\r\n");
                continue;
            }
        }

        rc = tiny_vm_exec(&vm, 128u);
        if (rc == TINY_VM_STEP_LIMIT) {
            continue;
        }
        if (rc == TINY_VM_HALT) {
            usart1_puts("tiny_vm: halt\r\n");
        } else if (rc < 0) {
            usart1_puts("tiny_vm: runtime error\r\n");
        }
        vm.code_len = 0u;
    }
}
