#include "clock.h"
#include "lpc111x_min.h"
#include "systick.h"
#include "tiny_vm.h"
#include "uart.h"

#include <stdint.h>

#define LED_PIN_BIT (1u << 0) /* PIO1_0 */

#define VM_UPLOAD_MAGIC0 'T'
#define VM_UPLOAD_MAGIC1 'V'
#define VM_UPLOAD_MAGIC2 'M'
#define VM_UPLOAD_MAGIC3 '1'

#define BOOT_UPLOAD_WINDOW_MS 5000u
#define BYTE_TIMEOUT_MS 250u
#define WAIT_FOREVER_MS 0xFFFFFFFFu

enum {
    HOST_LED_WRITE = 0,
    HOST_DELAY_MS = 1,
    HOST_UART_PRINTLN_U32 = 2
};

static void host_delay_ms(uint32_t ms)
{
    uint32_t start = systick_millis();
    while ((uint32_t)(systick_millis() - start) < ms) {
    }
}

static int uart_read_byte_timeout(uint8_t *out, uint32_t timeout_ms)
{
    uint32_t start = systick_millis();
    while (1) {
        if ((LPC_UART_LSR & (1u << 0)) != 0u) {
            *out = (uint8_t)(LPC_UART_RBR & 0xFFu);
            return 1;
        }
        if (timeout_ms != WAIT_FOREVER_MS) {
            if ((uint32_t)(systick_millis() - start) >= timeout_ms) {
                return 0;
            }
        }
    }
}

static int wait_magic_start(uint32_t timeout_ms)
{
    uint8_t b = 0;
    uint32_t start = systick_millis();
    while (1) {
        if (timeout_ms != WAIT_FOREVER_MS) {
            if ((uint32_t)(systick_millis() - start) >= timeout_ms) {
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
            LPC_GPIO1_DATA |= LED_PIN_BIT;
        } else {
            LPC_GPIO1_DATA &= ~LED_PIN_BIT;
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
            uart_putc('-');
            uart_put_dec_u32((uint32_t)(-v));
        } else {
            uart_put_dec_u32((uint32_t)v);
        }
        uart_puts("\r\n");
        return 0;
    default:
        return -1;
    }
}

static void led_init(void)
{
    LPC_IOCON_PIO1_0 &= ~0x7u;
    LPC_IOCON_PIO1_0 &= ~((0x3u << 3) | (1u << 10));
    LPC_GPIO1_DIR |= LED_PIN_BIT;
    LPC_GPIO1_DATA &= ~LED_PIN_BIT;
}

int main(void)
{
    tiny_vm_t vm;
    int rc;

    clock_init_48mhz();
    systick_init_1ms();
    uart_init_57600();
    led_init();

    tiny_vm_init(&vm, vm_host_call, 0);

    uart_puts("tiny_vm: upload frame TVM1+len+code+sum\r\n");
    uart_puts("tiny_vm: boot window 5s\r\n");

    rc = vm_receive_program(&vm, BOOT_UPLOAD_WINDOW_MS);
    if (rc == 0) {
        uart_puts("tiny_vm: no image in boot window\r\n");
    } else if (rc < 0) {
        uart_puts("tiny_vm: boot upload failed\r\n");
    } else {
        uart_puts("tiny_vm: image loaded\r\n");
    }

    while (1) {
        if (vm.code_len == 0u) {
            rc = vm_receive_program(&vm, WAIT_FOREVER_MS);
            if (rc > 0) {
                uart_puts("tiny_vm: image loaded\r\n");
            } else {
                uart_puts("tiny_vm: upload failed\r\n");
                continue;
            }
        }

        rc = tiny_vm_exec(&vm, 128u);
        if (rc == TINY_VM_STEP_LIMIT) {
            continue;
        }
        if (rc == TINY_VM_HALT) {
            uart_puts("tiny_vm: halt\r\n");
        } else if (rc < 0) {
            uart_puts("tiny_vm: runtime error\r\n");
        }
        vm.code_len = 0u; /* wait for next uploaded image */
    }
}
