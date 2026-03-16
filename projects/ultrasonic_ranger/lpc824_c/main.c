#include <stdbool.h>
#include <stdint.h>

#include "fsl_device_registers.h"

/*
 * GCC-native port of the legacy LPCXpresso/LPCOpen ultrasonic ranger:
 * `LPC824_Ultrasonic_Ranger/src/LPC824_Ultrasonic_Ranger.c`
 *
 * The firmware uses the LPC824 SCT to emit a short 40 kHz burst, then samples
 * the receive amplifier on ADC3, chaining three DMA descriptors to capture
 * 3072 16-bit ADC result words into SRAM. The packed sample stream is emitted
 * over USART0.
 *
 * Original design notes reference UM10800 chapters 11/12 (DMA), 16 (SCT), and
 * 21 (ADC). This port keeps the same hardware behavior but replaces the old
 * LPCOpen helpers with direct CMSIS register access.
 */

#ifndef ULTRASONIC_UART_BAUD_RATE
#define ULTRASONIC_UART_BAUD_RATE 230400u
#endif

#ifndef ULTRASONIC_ADC_CHANNEL
#define ULTRASONIC_ADC_CHANNEL 3u
#endif

#ifndef ULTRASONIC_ADC_SAMPLE_RATE
#define ULTRASONIC_ADC_SAMPLE_RATE 500000u
#endif

#ifndef ULTRASONIC_TRANSDUCER_FREQUENCY
#define ULTRASONIC_TRANSDUCER_FREQUENCY 40000u
#endif

#ifndef ULTRASONIC_PULSE_CYCLE_COUNT
#define ULTRASONIC_PULSE_CYCLE_COUNT 1u
#endif

#ifndef ULTRASONIC_DMA_BUFFER_SIZE
#define ULTRASONIC_DMA_BUFFER_SIZE 1024u
#endif

#define PIN_UART_RXD 0u
#define PIN_UART_TXD 4u
#define PIN_DEBUG 14u
#define PIN_TRANSDUCER_TX_A 15u
#define PIN_TRANSDUCER_TX_B 9u

#define DMA_CHANNEL_ADC 0u
#define ADC_SEQUENCE_A 0u

typedef struct {
    uint32_t xfercfg;
    uint32_t source;
    uint32_t dest;
    uint32_t next;
} dma_descriptor_t;

_Static_assert(sizeof(dma_descriptor_t) == 16u, "Unexpected DMA descriptor size");

static dma_descriptor_t g_dma_table[DMA_CHANNEL_COUNT] __attribute__((aligned(512)));
static dma_descriptor_t g_dma_desc_b __attribute__((aligned(16)));
static dma_descriptor_t g_dma_desc_c __attribute__((aligned(16)));

static uint16_t g_adc_buffer[ULTRASONIC_DMA_BUFFER_SIZE * 3u];

static volatile uint32_t g_dma_block_count;
static volatile uint32_t g_pulse_cycle_count;

static inline uint32_t pin_mask(uint32_t pin)
{
    return 1u << pin;
}

static inline uint32_t dma_channel_mask(uint32_t channel)
{
    return 1u << channel;
}

static inline void enable_clock(uint32_t mask)
{
    SYSCON->SYSAHBCLKCTRL |= mask;
}

static inline void peripheral_reset(uint32_t mask)
{
    SYSCON->PRESETCTRL &= ~mask;
    SYSCON->PRESETCTRL |= mask;
}

static inline void gpio_set_output(uint32_t pin)
{
    GPIO->DIRSET[0] = pin_mask(pin);
}

static inline void gpio_write(uint32_t pin, bool state)
{
    if (state) {
        GPIO->SET[0] = pin_mask(pin);
    } else {
        GPIO->CLR[0] = pin_mask(pin);
    }
}

static void debug_pin_pulse(uint32_t count)
{
    for (uint32_t i = 0; i < count; ++i) {
        gpio_write(PIN_DEBUG, true);
        gpio_write(PIN_DEBUG, false);
    }
}

static void usart0_assign_pins(void)
{
    uint32_t reg = SWM0->PINASSIGN.PINASSIGN0;

    reg &= ~(SWM_PINASSIGN0_U0_TXD_O_MASK | SWM_PINASSIGN0_U0_RXD_I_MASK);
    reg |= SWM_PINASSIGN0_U0_TXD_O(PIN_UART_TXD);
    reg |= SWM_PINASSIGN0_U0_RXD_I(PIN_UART_RXD);
    SWM0->PINASSIGN.PINASSIGN0 = reg;
}

static void sct_assign_transducer_pins(void)
{
    uint32_t reg7 = SWM0->PINASSIGN.PINASSIGN7;
    uint32_t reg8 = SWM0->PINASSIGN.PINASSIGN8;

    reg7 &= ~SWM_PINASSIGN7_SCT_OUT0_O_MASK;
    reg7 |= SWM_PINASSIGN7_SCT_OUT0_O(PIN_TRANSDUCER_TX_A);
    SWM0->PINASSIGN.PINASSIGN7 = reg7;

    reg8 &= ~SWM_PINASSIGN8_SCT_OUT1_O_MASK;
    reg8 |= SWM_PINASSIGN8_SCT_OUT1_O(PIN_TRANSDUCER_TX_B);
    SWM0->PINASSIGN.PINASSIGN8 = reg8;
}

static void adc3_enable_fixed_pin(void)
{
    SWM0->PINENABLE0 &= ~SWM_PINENABLE0_ADC_3_MASK;
}

static void usart0_configure_baud(uint32_t baud_rate)
{
    uint64_t best_error = UINT64_MAX;
    uint32_t best_brg = 0u;
    uint32_t best_mult = 0u;

    /*
     * FRG divider for LPC82x USARTs:
     *   U_PCLK = FCLK / (1 + MULT / DIV), with DIV fixed to 256 when DIV register
     *   is programmed to 0xFF. The USART baud generator then divides U_PCLK by
     *   16 * (BRG + 1) when OSR = 15.
     */
    SYSCON->UARTCLKDIV = SYSCON_UARTCLKDIV_DIV(1u);
    SYSCON->UARTFRGDIV = SYSCON_UARTFRGDIV_DIV(0xFFu);

    for (uint32_t mult = 0u; mult <= 0xFFu; ++mult) {
        const uint64_t numerator = (uint64_t)SystemCoreClock * 256u;
        const uint64_t denominator = (uint64_t)(256u + mult) * 16u * baud_rate;
        uint64_t brg_plus_one;
        uint64_t actual_baud;
        uint64_t error;

        if (denominator == 0u) {
            continue;
        }

        brg_plus_one = (numerator + (denominator / 2u)) / denominator;
        if (brg_plus_one == 0u) {
            brg_plus_one = 1u;
        }
        if (brg_plus_one > 65536u) {
            brg_plus_one = 65536u;
        }

        actual_baud = (numerator + (((uint64_t)(256u + mult) * 16u * brg_plus_one) / 2u)) /
                      ((uint64_t)(256u + mult) * 16u * brg_plus_one);

        error = (actual_baud > baud_rate) ? (actual_baud - baud_rate) : (baud_rate - actual_baud);
        if (error < best_error) {
            best_error = error;
            best_brg = (uint32_t)(brg_plus_one - 1u);
            best_mult = mult;
            if (error == 0u) {
                break;
            }
        }
    }

    USART0->OSR = USART_OSR_OSRVAL(15u);
    SYSCON->UARTFRGMULT = SYSCON_UARTFRGMULT_MULT(best_mult);
    USART0->BRG = USART_BRG_BRGVAL(best_brg);
}

static void usart0_init(void)
{
    enable_clock(SYSCON_SYSAHBCLKCTRL_SWM_MASK | SYSCON_SYSAHBCLKCTRL_UART0_MASK);
    peripheral_reset(SYSCON_PRESETCTRL_UARTFRG_RST_N_MASK | SYSCON_PRESETCTRL_UART0_RST_N_MASK);

    usart0_assign_pins();

    USART0->CFG = USART_CFG_DATALEN(1u) | USART_CFG_PARITYSEL(0u) | USART_CFG_STOPLEN(0u);
    USART0->CTL = 0u;
    usart0_configure_baud(ULTRASONIC_UART_BAUD_RATE);
    USART0->CFG |= USART_CFG_ENABLE_MASK;
}

static void uart_write_byte(uint8_t byte)
{
    while ((USART0->STAT & USART_STAT_TXRDY_MASK) == 0u) {
    }

    USART0->TXDAT = USART_TXDAT_TXDAT(byte);
}

static void uart_write_decimal(int32_t value)
{
    char buffer[12];
    uint32_t i = 0u;
    uint32_t magnitude;

    if (value == 0) {
        uart_write_byte('0');
        return;
    }

    if (value < 0) {
        uart_write_byte('-');
        magnitude = (uint32_t)(-value);
    } else {
        magnitude = (uint32_t)value;
    }

    while (magnitude > 0u) {
        buffer[i++] = (char)('0' + (magnitude % 10u));
        magnitude /= 10u;
    }

    while (i > 0u) {
        uart_write_byte((uint8_t)buffer[--i]);
    }
}

static void uart_write_string(const char *s)
{
    while (*s != '\0') {
        uart_write_byte((uint8_t)*s++);
    }
}

static void sct_halt(void)
{
    SCT0->CTRL |= SCT_CTRLL_HALT_L_MASK;
}

static void sct_run(void)
{
    SCT0->CTRL &= ~SCT_CTRLL_HALT_L_MASK;
}

static void sct_reset_block(void)
{
    enable_clock(SYSCON_SYSAHBCLKCTRL_SCT_MASK);
    peripheral_reset(SYSCON_PRESETCTRL_SCT_RST_N_MASK);
    sct_halt();
    SCT0->CTRL |= SCT_CTRLL_CLRCTR_L_MASK;
    SCT0->CTRL &= ~SCT_CTRLL_CLRCTR_L_MASK;
    SCT0->CONFIG = SCT_CONFIG_UNIFY(1u) | SCT_CONFIG_AUTOLIMIT_L(1u);
    SCT0->REGMODE = 0u;
    SCT0->OUTPUTDIRCTRL = 0u;
    SCT0->RES = 1u << 0;
    SCT0->EVFLAG = 0xFFFFFFFFu;
    SCT0->EVEN = 0u;
}

static void sct_configure_match_event(uint32_t event_index, uint32_t match_index)
{
    SCT0->EV[event_index].CTRL = SCT_EV_CTRL_MATCHSEL(match_index) | SCT_EV_CTRL_COMBMODE(1u);
    SCT0->EV[event_index].STATE = SCT_EV_STATE_STATEMSKn(1u);
}

static void sct_set_match(uint32_t match_index, uint32_t value)
{
    SCT0->MATCH[match_index] = value;
    SCT0->MATCHREL[match_index] = value;
}

static void setup_sct_for_transducer(void)
{
    const uint32_t half_period_ticks = SystemCoreClock / (ULTRASONIC_TRANSDUCER_FREQUENCY * 2u);

    sct_reset_block();
    sct_assign_transducer_pins();

    sct_configure_match_event(0u, 0u);
    sct_configure_match_event(2u, 2u);

    sct_set_match(2u, half_period_ticks);
    sct_set_match(0u, half_period_ticks * 2u);

    SCT0->OUT[0].SET = 1u << 0;
    SCT0->OUT[0].CLR = 1u << 2;
    SCT0->OUT[1].SET = 1u << 2;
    SCT0->OUT[1].CLR = 1u << 0;

    /* Count a full transducer period on event 0, which is the autolimit event. */
    SCT0->EVFLAG = 0xFFFFFFFFu;
    SCT0->EVEN = 1u << 0;
    NVIC_ClearPendingIRQ(SCT0_IRQn);
    NVIC_EnableIRQ(SCT0_IRQn);
}

static void setup_sct_for_adc(void)
{
    const uint32_t half_period_ticks = SystemCoreClock / (ULTRASONIC_ADC_SAMPLE_RATE * 2u);

    sct_reset_block();

    sct_configure_match_event(0u, 0u);
    sct_configure_match_event(2u, 2u);

    sct_set_match(2u, half_period_ticks);
    sct_set_match(0u, half_period_ticks * 2u);

    SCT0->OUT[3].SET = 1u << 0;
    SCT0->OUT[3].CLR = 1u << 2;

    NVIC_DisableIRQ(SCT0_IRQn);
}

static uint32_t dma_xfercfg(uint32_t transfer_count, bool reload, bool interrupt_a)
{
    uint32_t cfg = DMA_CHANNEL_XFERCFG_CFGVALID(1u) |
                   DMA_CHANNEL_XFERCFG_WIDTH(1u) |
                   DMA_CHANNEL_XFERCFG_SRCINC(0u) |
                   DMA_CHANNEL_XFERCFG_DSTINC(1u) |
                   DMA_CHANNEL_XFERCFG_XFERCOUNT(transfer_count - 1u);

    if (reload) {
        cfg |= DMA_CHANNEL_XFERCFG_RELOAD(1u);
    }
    if (interrupt_a) {
        cfg |= DMA_CHANNEL_XFERCFG_SETINTA(1u);
    }

    return cfg;
}

static void setup_dma_for_adc(void)
{
    const uint32_t sample_reg = (uint32_t)&ADC0->DAT[ULTRASONIC_ADC_CHANNEL];
    const uint32_t channel_mask = dma_channel_mask(DMA_CHANNEL_ADC);

    enable_clock(SYSCON_SYSAHBCLKCTRL_DMA_MASK);
    peripheral_reset(SYSCON_PRESETCTRL_DMA_RST_N_MASK);

    g_dma_desc_c.xfercfg = dma_xfercfg(ULTRASONIC_DMA_BUFFER_SIZE, false, true);
    g_dma_desc_c.source = sample_reg;
    g_dma_desc_c.dest = (uint32_t)&g_adc_buffer[(ULTRASONIC_DMA_BUFFER_SIZE * 3u) - 1u];
    g_dma_desc_c.next = 0u;

    g_dma_desc_b.xfercfg = dma_xfercfg(ULTRASONIC_DMA_BUFFER_SIZE, true, true);
    g_dma_desc_b.source = sample_reg;
    g_dma_desc_b.dest = (uint32_t)&g_adc_buffer[(ULTRASONIC_DMA_BUFFER_SIZE * 2u) - 1u];
    g_dma_desc_b.next = (uint32_t)&g_dma_desc_c;

    g_dma_table[DMA_CHANNEL_ADC].xfercfg = dma_xfercfg(ULTRASONIC_DMA_BUFFER_SIZE, true, true);
    g_dma_table[DMA_CHANNEL_ADC].source = sample_reg;
    g_dma_table[DMA_CHANNEL_ADC].dest = (uint32_t)&g_adc_buffer[ULTRASONIC_DMA_BUFFER_SIZE - 1u];
    g_dma_table[DMA_CHANNEL_ADC].next = (uint32_t)&g_dma_desc_b;

    DMA0->CTRL = DMA_CTRL_ENABLE(1u);
    DMA0->SRAMBASE = DMA_SRAMBASE_OFFSET(((uint32_t)g_dma_table) >> DMA_SRAMBASE_OFFSET_SHIFT);

    DMA0->COMMON[0].ENABLECLR = channel_mask;
    DMA0->COMMON[0].ABORT = channel_mask;
    DMA0->COMMON[0].INTA = channel_mask;
    DMA0->COMMON[0].INTB = channel_mask;
    DMA0->COMMON[0].ERRINT = channel_mask;
    DMA0->COMMON[0].INTENSET = channel_mask;

    DMA0->CHANNEL[DMA_CHANNEL_ADC].CFG =
        DMA_CHANNEL_CFG_HWTRIGEN(1u) |
        DMA_CHANNEL_CFG_TRIGPOL(1u) |
        DMA_CHANNEL_CFG_TRIGTYPE(0u) |
        DMA_CHANNEL_CFG_TRIGBURST(1u) |
        DMA_CHANNEL_CFG_BURSTPOWER(0u) |
        DMA_CHANNEL_CFG_CHPRIORITY(0u);
    DMA0->CHANNEL[DMA_CHANNEL_ADC].XFERCFG = g_dma_table[DMA_CHANNEL_ADC].xfercfg;

    INPUTMUX->DMA_ITRIG_INMUX[DMA_CHANNEL_ADC] = INPUTMUX_DMA_ITRIG_INMUX_INP(0u);

    DMA0->COMMON[0].SETVALID = channel_mask;
    DMA0->COMMON[0].ENABLESET = channel_mask;

    NVIC_ClearPendingIRQ(DMA0_IRQn);
    NVIC_EnableIRQ(DMA0_IRQn);
}

static void adc_init(void)
{
    enable_clock(SYSCON_SYSAHBCLKCTRL_IOCON_MASK |
                 SYSCON_SYSAHBCLKCTRL_SWM_MASK |
                 SYSCON_SYSAHBCLKCTRL_ADC_MASK);
    peripheral_reset(SYSCON_PRESETCTRL_ADC_RST_N_MASK);

    /*
     * LPCOpen's Chip_ADC_Init() powers the ADC analog block up before
     * calibration. Without this, CALMODE never completes and the port stalls
     * here.
     */
    SYSCON->PDAWAKECFG &= ~SYSCON_PDAWAKECFG_ADC_PD_MASK;
    SYSCON->PDRUNCFG &= ~SYSCON_PDRUNCFG_ADC_PD_MASK;

    /*
     * Disable pull resistors on ADC3 / PIO0_23. The legacy firmware relied on
     * this to stop the input drifting toward VDD.
     */
    IOCON->PIO[IOCON_INDEX_PIO0_23] =
        (IOCON->PIO[IOCON_INDEX_PIO0_23] & ~IOCON_PIO_MODE_MASK) |
        IOCON_PIO_MODE(0u);

    adc3_enable_fixed_pin();

    ADC0->CTRL = ADC_CTRL_CLKDIV(0u);
    ADC0->CTRL |= ADC_CTRL_CALMODE(1u);
    while ((ADC0->CTRL & ADC_CTRL_CALMODE_MASK) != 0u) {
    }

    ADC0->SEQ_CTRL[ADC_SEQUENCE_A] =
        ADC_SEQ_CTRL_CHANNELS(1u << ULTRASONIC_ADC_CHANNEL) |
        ADC_SEQ_CTRL_TRIGGER(3u) |
        ADC_SEQ_CTRL_MODE(1u) |
        ADC_SEQ_CTRL_SEQ_ENA(1u);
    ADC0->INTEN = ADC_INTEN_SEQA_INTEN(1u);
    ADC0->FLAGS = 0xFFFFFFFFu;
}

void DMA0_IRQHandler(void)
{
    debug_pin_pulse(8u);
    DMA0->COMMON[0].INTA = dma_channel_mask(DMA_CHANNEL_ADC);
    ++g_dma_block_count;
}

void SCT0_IRQHandler(void)
{
    ++g_pulse_cycle_count;
    debug_pin_pulse(1u);
    SCT0->EVFLAG = 1u << 0;
}

int main(void)
{
    SystemCoreClockUpdate();

    enable_clock(SYSCON_SYSAHBCLKCTRL_GPIO_MASK);
    gpio_set_output(PIN_DEBUG);
    gpio_set_output(PIN_TRANSDUCER_TX_A);
    gpio_set_output(PIN_TRANSDUCER_TX_B);
    gpio_write(PIN_TRANSDUCER_TX_A, false);

    usart0_init();
    uart_write_string("ultrasonic: boot\r\n");
    adc_init();
    uart_write_string("ultrasonic: adc-init-done\r\n");

    while (1) {
        //uart_write_string("ultrasonic: tx-burst\r\n");
        setup_sct_for_transducer();
        g_pulse_cycle_count = 0u;
        debug_pin_pulse(2u);
        sct_run();
        while (g_pulse_cycle_count < ULTRASONIC_PULSE_CYCLE_COUNT) {
            __WFI();
        }
        sct_halt();
        //uart_write_string("ultrasonic: tx-burst-done\r\n");

        //uart_write_string("ultrasonic: dma-start\r\n");
        setup_dma_for_adc();
        setup_sct_for_adc();

        g_dma_block_count = 0u;
        sct_run();
        while (g_dma_block_count < 3u) {
            __WFI();
        }
        sct_halt();
        //uart_write_string("ultrasonic: dma-done\r\n");

        for (uint32_t i = 0u; i < (ULTRASONIC_DMA_BUFFER_SIZE * 3u); ++i) {
            g_adc_buffer[i] >>= 4u;
        }

        uart_write_byte('W');
        uart_write_byte(' ');
        for (uint32_t i = 0u; i < (ULTRASONIC_DMA_BUFFER_SIZE * 3u); ++i) {
            uart_write_byte((uint8_t)(((g_adc_buffer[i] >> 6u) & 0x3Fu) + '?'));
            uart_write_byte((uint8_t)((g_adc_buffer[i] & 0x3Fu) + '?'));
        }
        uart_write_byte('\r');
        uart_write_byte('\n');

        /*
         * Keep the decimal printer linked in the first migration step. It is
         * useful for quick instrumentation while validating the new build.
         */
        if (false) {
            uart_write_decimal(0);
        }
    }
}
