#include <stdint.h>

extern uint32_t _sidata;
extern uint32_t _sdata;
extern uint32_t _edata;
extern uint32_t _sbss;
extern uint32_t _ebss;
extern uint32_t _estack;

void Reset_Handler(void);
void Default_Handler(void);

void NMI_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)    __attribute__((weak, alias("Default_Handler")));
void WAKEUP_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
void CAN_IRQHandler(void)     __attribute__((weak, alias("Default_Handler")));
void SSP1_IRQHandler(void)    __attribute__((weak, alias("Default_Handler")));
void I2C_IRQHandler(void)     __attribute__((weak, alias("Default_Handler")));
void CT16B0_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
void CT16B1_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
void CT32B0_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
void CT32B1_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
void SSP0_IRQHandler(void)    __attribute__((weak, alias("Default_Handler")));
void UART_IRQHandler(void)    __attribute__((weak, alias("Default_Handler")));
void USB_IRQHandler(void)     __attribute__((weak, alias("Default_Handler")));
void USB_FIQHandler(void)     __attribute__((weak, alias("Default_Handler")));
void ADC_IRQHandler(void)     __attribute__((weak, alias("Default_Handler")));
void WDT_IRQHandler(void)     __attribute__((weak, alias("Default_Handler")));
void BOD_IRQHandler(void)     __attribute__((weak, alias("Default_Handler")));
void FMC_IRQHandler(void)     __attribute__((weak, alias("Default_Handler")));
void PIOINT3_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void PIOINT2_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void PIOINT1_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void PIOINT0_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));

int main(void);

__attribute__((section(".isr_vector")))
void (* const g_pfnVectors[])(void) = {
    (void (*)(void))(&_estack),
    Reset_Handler,
    NMI_Handler,
    HardFault_Handler,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    SVC_Handler,
    0,
    0,
    PendSV_Handler,
    SysTick_Handler,
    WAKEUP_IRQHandler,  /* 16 PIO0_0 */
    WAKEUP_IRQHandler,  /* 17 PIO0_1 */
    WAKEUP_IRQHandler,  /* 18 PIO0_2 */
    WAKEUP_IRQHandler,  /* 19 PIO0_3 */
    WAKEUP_IRQHandler,  /* 20 PIO0_4 */
    WAKEUP_IRQHandler,  /* 21 PIO0_5 */
    WAKEUP_IRQHandler,  /* 22 PIO0_6 */
    WAKEUP_IRQHandler,  /* 23 PIO0_7 */
    WAKEUP_IRQHandler,  /* 24 PIO0_8 */
    WAKEUP_IRQHandler,  /* 25 PIO0_9 */
    WAKEUP_IRQHandler,  /* 26 PIO0_10 */
    WAKEUP_IRQHandler,  /* 27 PIO0_11 */
    WAKEUP_IRQHandler,  /* 28 PIO1_0 */
    CAN_IRQHandler,     /* 29 */
    SSP1_IRQHandler,    /* 30 */
    I2C_IRQHandler,     /* 31 */
    CT16B0_IRQHandler,  /* 32 */
    CT16B1_IRQHandler,  /* 33 */
    CT32B0_IRQHandler,  /* 34 */
    CT32B1_IRQHandler,  /* 35 */
    SSP0_IRQHandler,    /* 36 */
    UART_IRQHandler,    /* 37 */
    USB_IRQHandler,     /* 38 */
    USB_FIQHandler,     /* 39 */
    ADC_IRQHandler,     /* 40 */
    WDT_IRQHandler,     /* 41 */
    BOD_IRQHandler,     /* 42 */
    FMC_IRQHandler,     /* 43 */
    PIOINT3_IRQHandler, /* 44 */
    PIOINT2_IRQHandler, /* 45 */
    PIOINT1_IRQHandler, /* 46 */
    PIOINT0_IRQHandler, /* 47 */
};

static void data_init(void)
{
    uint32_t *src = &_sidata;
    uint32_t *dst = &_sdata;
    while (dst < &_edata) {
        *dst++ = *src++;
    }
}

static void bss_init(void)
{
    uint32_t *dst = &_sbss;
    while (dst < &_ebss) {
        *dst++ = 0;
    }
}

void Reset_Handler(void)
{
    data_init();
    bss_init();
    (void)main();
    while (1) {
        __asm__ volatile ("wfi");
    }
}

void Default_Handler(void)
{
    while (1) {
        __asm__ volatile ("wfi");
    }
}
