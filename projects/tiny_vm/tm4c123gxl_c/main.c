#include <stdint.h>

#include "tiny_vm.h"
#include "tm4c123gh6pm.h"

#define LED_PIN_BIT TM4C123_PF1_RED_LED
#define TINY_VM_ACTIVITY_LED 1

#define VM_UPLOAD_MAGIC0 'T'
#define VM_UPLOAD_MAGIC1 'V'
#define VM_UPLOAD_MAGIC2 'M'
#define VM_UPLOAD_MAGIC3 '1'

#define BOOT_UPLOAD_WINDOW_MS 15000u
#define BYTE_TIMEOUT_MS 250u
#define WAIT_FOREVER_MS 0xFFFFFFFFu

#define UART_BAUD_115200_IBRD 8u
#define UART_BAUD_115200_FBRD 44u

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

static void systick_init_1ms(void)
{
    NVIC_ST_RELOAD_R = 16000u - 1u;
    NVIC_ST_CURRENT_R = 0u;
    NVIC_ST_CTRL_R = NVIC_ST_CTRL_CLK_SRC | NVIC_ST_CTRL_INTEN | NVIC_ST_CTRL_ENABLE;
}

static void uart0_init_115200(void)
{
    SYSCTL_RCGCGPIO_R |= (1u << TM4C123_PORTA_BIT);
    SYSCTL_RCGCUART_R |= (1u << 0);

    while ((SYSCTL_PRGPIO_R & (1u << TM4C123_PORTA_BIT)) == 0u) {
        /* Wait until GPIO Port A leaves reset. */
    }
    while ((SYSCTL_PRUART_R & (1u << 0)) == 0u) {
        /* Wait until UART0 leaves reset. */
    }

    UART0_CTL_R &= ~(UART_CTL_UARTEN | UART_CTL_TXE | UART_CTL_RXE);
    UART0_CC_R = UART_CC_CS_PIOSC;
    UART0_IBRD_R = UART_BAUD_115200_IBRD;
    UART0_FBRD_R = UART_BAUD_115200_FBRD;
    UART0_LCRH_R = UART_LCRH_WLEN_8 | UART_LCRH_FEN;

    GPIO_PORTA_AMSEL_R &= ~(TM4C123_PA0_U0RX | TM4C123_PA1_U0TX);
    GPIO_PORTA_PCTL_R &= ~0x000000FFu;
    GPIO_PORTA_PCTL_R |= 0x00000011u;
    GPIO_PORTA_AFSEL_R |= TM4C123_PA0_U0RX | TM4C123_PA1_U0TX;
    GPIO_PORTA_DEN_R |= TM4C123_PA0_U0RX | TM4C123_PA1_U0TX;
    GPIO_PORTA_DR2R_R |= TM4C123_PA1_U0TX;
    GPIO_PORTA_DIR_R &= ~TM4C123_PA0_U0RX;
    GPIO_PORTA_DIR_R |= TM4C123_PA1_U0TX;

    UART0_CTL_R = UART_CTL_UARTEN | UART_CTL_TXE | UART_CTL_RXE;
}

static void uart0_putc(char ch)
{
    while ((UART0_FR_R & UART_FR_TXFF) != 0u) {
        /* Wait for space in the transmit FIFO. */
    }
    UART0_DR_R = (uint32_t)(uint8_t)ch;
}

static void uart0_puts(const char *text)
{
    while (*text != '\0') {
        uart0_putc(*text++);
    }
}

static void uart0_put_hex8(uint8_t value)
{
    static const char hex[] = "0123456789ABCDEF";
    uart0_putc(hex[(value >> 4) & 0x0Fu]);
    uart0_putc(hex[value & 0x0Fu]);
}

static void uart0_put_dec_u32(uint32_t value)
{
    char buffer[10];
    uint32_t i = 0u;

    if (value == 0u) {
        uart0_putc('0');
        return;
    }

    while (value != 0u) {
        buffer[i++] = (char)('0' + (value % 10u));
        value /= 10u;
    }

    while (i > 0u) {
        uart0_putc(buffer[--i]);
    }
}

static void host_delay_ms(uint32_t ms)
{
    delay_ms(ms);
}

static int uart_read_byte_timeout(uint8_t *out, uint32_t timeout_ms)
{
    uint32_t start = g_ms_ticks;
    while (1) {
        if ((UART0_FR_R & UART_FR_RXFE) == 0u) {
            *out = (uint8_t)(UART0_DR_R & 0xFFu);
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
        if (v != 0) {
            GPIO_PORTF_DATA_R |= LED_PIN_BIT;
        } else {
            GPIO_PORTF_DATA_R &= ~LED_PIN_BIT;
        }
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
            uart0_putc('-');
            uart0_put_dec_u32((uint32_t)(-v));
        } else {
            uart0_put_dec_u32((uint32_t)v);
        }
        uart0_puts("\r\n");
        return 0;
    case HOST_UART_PRINTLN_HEX32: {
        uint32_t uv;
        if (tiny_vm_pop(vm, &v) < 0) {
            return -1;
        }
        uv = (uint32_t)v;
        uart0_put_hex8((uint8_t)((uv >> 24) & 0xFFu));
        uart0_put_hex8((uint8_t)((uv >> 16) & 0xFFu));
        uart0_put_hex8((uint8_t)((uv >> 8) & 0xFFu));
        uart0_put_hex8((uint8_t)(uv & 0xFFu));
        uart0_puts("\r\n");
        return 0;
    }
    default:
        return -1;
    }
}

static void led_init(void)
{
    SYSCTL_RCGCGPIO_R |= (1u << TM4C123_PORTF_BIT);
    while ((SYSCTL_PRGPIO_R & (1u << TM4C123_PORTF_BIT)) == 0u) {
        /* Wait until Port F leaves reset. */
    }

    GPIO_PORTF_LOCK_R = 0x4C4F434Bu;
    GPIO_PORTF_CR_R |= LED_PIN_BIT;
    GPIO_PORTF_AMSEL_R &= ~LED_PIN_BIT;
    GPIO_PORTF_PCTL_R &= ~(0xFu << 4);
    GPIO_PORTF_AFSEL_R &= ~LED_PIN_BIT;
    GPIO_PORTF_DIR_R |= LED_PIN_BIT;
    GPIO_PORTF_DR2R_R |= LED_PIN_BIT;
    GPIO_PORTF_DEN_R |= LED_PIN_BIT;
    GPIO_PORTF_DATA_R &= ~LED_PIN_BIT;
}

#if TINY_VM_ACTIVITY_LED
static void vm_trace_led_hook(tiny_vm_t *vm, uint8_t op, void *ctx)
{
    (void)vm;
    (void)op;
    (void)ctx;
    GPIO_PORTF_DATA_R ^= LED_PIN_BIT;
}
#endif

int main(void)
{
    tiny_vm_t vm;
    int rc;

    systick_init_1ms();
    uart0_init_115200();
    led_init();

    tiny_vm_init(&vm, vm_host_call, 0);
#if TINY_VM_ACTIVITY_LED
    tiny_vm_set_trace_hook(&vm, vm_trace_led_hook, 0);
#endif

    uart0_puts("tiny_vm: upload frame TVM1+len+code+sum\r\n");
    uart0_puts("tiny_vm: boot window 15s\r\n");

    rc = vm_receive_program(&vm, BOOT_UPLOAD_WINDOW_MS);
    if (rc < 0) {
        uart0_puts("tiny_vm: boot upload failed\r\n");
    } else {
        uart0_puts("tiny_vm: image loaded\r\n");
    }

    while (1) {
        if (vm.code_len == 0u) {
            rc = vm_receive_program(&vm, WAIT_FOREVER_MS);
            if (rc > 0) {
                uart0_puts("tiny_vm: image loaded\r\n");
            } else {
                uart0_puts("tiny_vm: upload failed\r\n");
                continue;
            }
        }

        rc = tiny_vm_exec(&vm, 128u);
        if (rc == TINY_VM_STEP_LIMIT) {
            continue;
        }
        if (rc == TINY_VM_HALT) {
            uart0_puts("tiny_vm: halt\r\n");
        } else if (rc < 0) {
            uart0_puts("tiny_vm: runtime error\r\n");
        }
        vm.code_len = 0u;
    }
}
