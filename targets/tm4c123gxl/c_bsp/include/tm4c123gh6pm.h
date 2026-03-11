#ifndef TM4C123GH6PM_H
#define TM4C123GH6PM_H

#include <stdint.h>

#define HWREG32(addr) (*((volatile uint32_t *)(addr)))

/* System control */
#define SYSCTL_RCGCUART_R    HWREG32(0x400FE618u)
#define SYSCTL_RCGCGPIO_R    HWREG32(0x400FE608u)
#define SYSCTL_PRUART_R      HWREG32(0x400FEA18u)
#define SYSCTL_PRGPIO_R      HWREG32(0x400FEA08u)

/* GPIO Port A */
#define GPIO_PORTA_DATA_R    HWREG32(0x400043FCu)
#define GPIO_PORTA_DIR_R     HWREG32(0x40004400u)
#define GPIO_PORTA_AFSEL_R   HWREG32(0x40004420u)
#define GPIO_PORTA_DR2R_R    HWREG32(0x40004500u)
#define GPIO_PORTA_DEN_R     HWREG32(0x4000451Cu)
#define GPIO_PORTA_AMSEL_R   HWREG32(0x40004528u)
#define GPIO_PORTA_PCTL_R    HWREG32(0x4000452Cu)

/* GPIO Port F */
#define GPIO_PORTF_DATA_R    HWREG32(0x400253FCu)
#define GPIO_PORTF_DIR_R     HWREG32(0x40025400u)
#define GPIO_PORTF_AFSEL_R   HWREG32(0x40025420u)
#define GPIO_PORTF_DR2R_R    HWREG32(0x40025500u)
#define GPIO_PORTF_DEN_R     HWREG32(0x4002551Cu)
#define GPIO_PORTF_LOCK_R    HWREG32(0x40025520u)
#define GPIO_PORTF_CR_R      HWREG32(0x40025524u)
#define GPIO_PORTF_AMSEL_R   HWREG32(0x40025528u)
#define GPIO_PORTF_PCTL_R    HWREG32(0x4002552Cu)

/* SysTick */
#define NVIC_ST_CTRL_R       HWREG32(0xE000E010u)
#define NVIC_ST_RELOAD_R     HWREG32(0xE000E014u)
#define NVIC_ST_CURRENT_R    HWREG32(0xE000E018u)

#define NVIC_ST_CTRL_ENABLE  (1u << 0)
#define NVIC_ST_CTRL_INTEN   (1u << 1)
#define NVIC_ST_CTRL_CLK_SRC (1u << 2)

#define TM4C123_PORTA_BIT    0u
#define TM4C123_PORTF_BIT    5u
#define TM4C123_PA0_U0RX     (1u << 0)
#define TM4C123_PA1_U0TX     (1u << 1)
#define TM4C123_PF1_RED_LED  (1u << 1)

/* UART0 */
#define UART0_DR_R           HWREG32(0x4000C000u)
#define UART0_FR_R           HWREG32(0x4000C018u)
#define UART0_IBRD_R         HWREG32(0x4000C024u)
#define UART0_FBRD_R         HWREG32(0x4000C028u)
#define UART0_LCRH_R         HWREG32(0x4000C02Cu)
#define UART0_CTL_R          HWREG32(0x4000C030u)
#define UART0_CC_R           HWREG32(0x4000CFC8u)

#define UART_FR_TXFF         (1u << 5)

#define UART_LCRH_FEN        (1u << 4)
#define UART_LCRH_WLEN_8     (3u << 5)

#define UART_CTL_UARTEN      (1u << 0)
#define UART_CTL_TXE         (1u << 8)
#define UART_CTL_RXE         (1u << 9)

#define UART_CC_CS_SYSCLK    0x0u
#define UART_CC_CS_PIOSC     0x5u

#endif
