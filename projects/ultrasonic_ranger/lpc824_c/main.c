#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "fsl_device_registers.h"

/*
 * GCC-native port of the legacy LPCXpresso/LPCOpen ultrasonic ranger:
 * `LPC824_Ultrasonic_Ranger/src/LPC824_Ultrasonic_Ranger.c`
 *
 * This version adds a lightweight UART control protocol using AT-style
 * commands while preserving the original compact `W ` waveform stream format
 * as the default output.
 */

#ifndef ULTRASONIC_UART_BAUD_RATE
#define ULTRASONIC_UART_BAUD_RATE 230400u
#endif

#ifndef ULTRASONIC_ADC_CHANNEL
#define ULTRASONIC_ADC_CHANNEL 3u
#endif

#ifndef ULTRASONIC_ADC_SAMPLE_RATE_DEFAULT
#define ULTRASONIC_ADC_SAMPLE_RATE_DEFAULT 500000u
#endif

#ifndef ULTRASONIC_TRANSDUCER_FREQUENCY_DEFAULT
#define ULTRASONIC_TRANSDUCER_FREQUENCY_DEFAULT 40000u
#endif

#ifndef ULTRASONIC_PULSE_CYCLE_COUNT_DEFAULT
#define ULTRASONIC_PULSE_CYCLE_COUNT_DEFAULT 1u
#endif

#ifndef ULTRASONIC_DMA_BUFFER_SIZE
#define ULTRASONIC_DMA_BUFFER_SIZE 1024u
#endif

#define ULTRASONIC_SAMPLE_COUNT (ULTRASONIC_DMA_BUFFER_SIZE * 3u)
#define ULTRASONIC_PROTOCOL_VERSION 1u
#define AT_COMMAND_BUFFER_SIZE 96u
#define AT_TXFREQ_MIN_HZ 1000u
#define AT_TXFREQ_MAX_HZ 100000u
#define AT_TXCYCLES_MIN 1u
#define AT_TXCYCLES_MAX 255u
#define AT_SRATE_MIN_HZ 10000u
#define AT_SRATE_MAX_HZ 1000000u

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

typedef enum {
    CAPTURE_MODE_SINGLE = 0,
    CAPTURE_MODE_NSHOT,
    CAPTURE_MODE_CONTINUOUS,
} capture_mode_t;

typedef enum {
    OUTPUT_FORMAT_COMPACT = 0,
    OUTPUT_FORMAT_TEXT,
    OUTPUT_FORMAT_BIN,
    OUTPUT_FORMAT_ENV,
} output_format_t;

typedef struct {
    capture_mode_t mode;
    output_format_t format;
    uint32_t nshot;
    uint32_t tx_frequency_hz;
    uint32_t tx_cycles;
    uint32_t adc_sample_rate_hz;
    uint32_t sample_count;
} ultrasonic_config_t;

_Static_assert(sizeof(dma_descriptor_t) == 16u, "Unexpected DMA descriptor size");

static dma_descriptor_t g_dma_table[DMA_CHANNEL_COUNT] __attribute__((aligned(512)));
static dma_descriptor_t g_dma_desc_b __attribute__((aligned(16)));
static dma_descriptor_t g_dma_desc_c __attribute__((aligned(16)));

static uint16_t g_adc_buffer[ULTRASONIC_SAMPLE_COUNT];
static uint32_t g_output_sample_count = ULTRASONIC_SAMPLE_COUNT;

static volatile uint32_t g_dma_block_count;
static volatile uint32_t g_pulse_cycle_count;

static ultrasonic_config_t g_config = {
    .mode = CAPTURE_MODE_CONTINUOUS,
    .format = OUTPUT_FORMAT_COMPACT,
    .nshot = 1u,
    .tx_frequency_hz = ULTRASONIC_TRANSDUCER_FREQUENCY_DEFAULT,
    .tx_cycles = ULTRASONIC_PULSE_CYCLE_COUNT_DEFAULT,
    .adc_sample_rate_hz = ULTRASONIC_ADC_SAMPLE_RATE_DEFAULT,
    .sample_count = ULTRASONIC_SAMPLE_COUNT,
};
static const ultrasonic_config_t g_default_config = {
    .mode = CAPTURE_MODE_CONTINUOUS,
    .format = OUTPUT_FORMAT_COMPACT,
    .nshot = 1u,
    .tx_frequency_hz = ULTRASONIC_TRANSDUCER_FREQUENCY_DEFAULT,
    .tx_cycles = ULTRASONIC_PULSE_CYCLE_COUNT_DEFAULT,
    .adc_sample_rate_hz = ULTRASONIC_ADC_SAMPLE_RATE_DEFAULT,
    .sample_count = ULTRASONIC_SAMPLE_COUNT,
};

static bool g_continuous_active = true;
static uint32_t g_pending_frames = 0u;
static uint32_t g_frame_sequence = 0u;
static char g_command_buffer[AT_COMMAND_BUFFER_SIZE];
static char g_pending_command_buffer[AT_COMMAND_BUFFER_SIZE];
static uint32_t g_command_length = 0u;
static bool g_command_overflow = false;
static bool g_pending_command_ready = false;
static bool g_pending_command_toolong = false;
static bool g_pending_command_dropped = false;

static void pump_uart_rx(void);
static void service_pending_command(void);

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

static const char *mode_to_string(capture_mode_t mode)
{
    switch (mode) {
    case CAPTURE_MODE_SINGLE:
        return "SINGLE";
    case CAPTURE_MODE_NSHOT:
        return "NSHOT";
    case CAPTURE_MODE_CONTINUOUS:
        return "CONTINUOUS";
    default:
        return "UNKNOWN";
    }
}

static const char *format_to_string(output_format_t format)
{
    switch (format) {
    case OUTPUT_FORMAT_COMPACT:
        return "COMPACT";
    case OUTPUT_FORMAT_TEXT:
        return "TEXT";
    case OUTPUT_FORMAT_BIN:
        return "BIN";
    case OUTPUT_FORMAT_ENV:
        return "ENV";
    default:
        return "UNKNOWN";
    }
}

static bool parse_u32(const char *text, uint32_t *value_out)
{
    uint32_t value = 0u;
    const char *cursor = text;

    if (*cursor == '\0') {
        return false;
    }

    while (*cursor != '\0') {
        const char ch = *cursor++;
        if (ch < '0' || ch > '9') {
            return false;
        }
        value = (value * 10u) + (uint32_t)(ch - '0');
    }

    *value_out = value;
    return true;
}

static bool string_equals(const char *lhs, const char *rhs)
{
    return strcmp(lhs, rhs) == 0;
}

static bool string_starts_with(const char *text, const char *prefix)
{
    const size_t prefix_len = strlen(prefix);
    return strncmp(text, prefix, prefix_len) == 0;
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

static bool uart_rx_ready(void)
{
    return (USART0->STAT & USART_STAT_RXRDY_MASK) != 0u;
}

static uint8_t uart_read_byte(void)
{
    return (uint8_t)((USART0->RXDAT & USART_RXDAT_RXDAT_MASK) >> USART_RXDAT_RXDAT_SHIFT);
}

static void uart_write_byte(uint8_t byte)
{
    while ((USART0->STAT & USART_STAT_TXRDY_MASK) == 0u) {
        pump_uart_rx();
    }

    USART0->TXDAT = USART_TXDAT_TXDAT(byte);
    pump_uart_rx();
}

static void uart_write_data(const uint8_t *data, uint32_t length)
{
    for (uint32_t i = 0u; i < length; ++i) {
        uart_write_byte(data[i]);
    }
}

static void uart_write_decimal(uint32_t value)
{
    char buffer[12];
    uint32_t i = 0u;

    if (value == 0u) {
        uart_write_byte('0');
        return;
    }

    while (value > 0u) {
        buffer[i++] = (char)('0' + (value % 10u));
        value /= 10u;
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

static void uart_wait_tx_idle(void)
{
    while ((USART0->STAT & USART_STAT_TXIDLE_MASK) == 0u) {
        pump_uart_rx();
    }
}

static void uart_write_crlf(void)
{
    uart_write_byte('\r');
    uart_write_byte('\n');
}

static void emit_ok(void)
{
    uart_write_string("OK");
    uart_write_crlf();
}

static void emit_error(const char *reason)
{
    uart_write_string("ERROR");
    if (reason != NULL && *reason != '\0') {
        uart_write_byte(':');
        uart_write_string(reason);
    }
    uart_write_crlf();
}

static void emit_info(void)
{
    uart_write_string("+INFO: proto=");
    uart_write_decimal(ULTRASONIC_PROTOCOL_VERSION);
    uart_write_string(",target=LPC824,fw=ultrasonic_ranger");
    uart_write_crlf();
}

static uint32_t estimate_envelope_sample_count(void)
{
    const uint64_t numerator =
        ((uint64_t)g_config.sample_count * (uint64_t)g_config.tx_frequency_hz) +
        ((uint64_t)g_config.adc_sample_rate_hz - 1u);
    return (uint32_t)(numerator / (uint64_t)g_config.adc_sample_rate_hz);
}

static void emit_config(void)
{
    uart_write_string("+CFG: mode=");
    uart_write_string(mode_to_string(g_config.mode));
    uart_write_string(",nshot=");
    uart_write_decimal(g_config.nshot);
    uart_write_string(",fmt=");
    uart_write_string(format_to_string(g_config.format));
    uart_write_string(",txfreq=");
    uart_write_decimal(g_config.tx_frequency_hz);
    uart_write_string(",txcycles=");
    uart_write_decimal(g_config.tx_cycles);
    uart_write_string(",srate=");
    uart_write_decimal(g_config.adc_sample_rate_hz);
    uart_write_string(",samples=");
    uart_write_decimal(g_config.sample_count);
    uart_write_string(",envsamples=");
    uart_write_decimal(estimate_envelope_sample_count());
    uart_write_crlf();
}

static void emit_done_frames(uint32_t frame_count)
{
    uart_write_string("+DONE: frames=");
    uart_write_decimal(frame_count);
    uart_write_crlf();
}

static void emit_done_stopped(void)
{
    uart_write_string("+DONE: stopped");
    uart_write_crlf();
}

static void emit_query_value(const char *name, const char *value)
{
    uart_write_byte('+');
    uart_write_string(name);
    uart_write_string(": ");
    uart_write_string(value);
    uart_write_crlf();
}

static void emit_query_value_u32(const char *name, uint32_t value)
{
    uart_write_byte('+');
    uart_write_string(name);
    uart_write_string(": ");
    uart_write_decimal(value);
    uart_write_crlf();
}

static bool capture_is_active(void)
{
    return g_continuous_active || (g_pending_frames > 0u);
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
    const uint32_t half_period_ticks = SystemCoreClock / (g_config.tx_frequency_hz * 2u);

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

    SCT0->EVFLAG = 0xFFFFFFFFu;
    SCT0->EVEN = 1u << 0;
    NVIC_ClearPendingIRQ(SCT0_IRQn);
    NVIC_EnableIRQ(SCT0_IRQn);
}

static void setup_sct_for_adc(void)
{
    const uint32_t half_period_ticks = SystemCoreClock / (g_config.adc_sample_rate_hz * 2u);

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

    SYSCON->PDAWAKECFG &= ~SYSCON_PDAWAKECFG_ADC_PD_MASK;
    SYSCON->PDRUNCFG &= ~SYSCON_PDRUNCFG_ADC_PD_MASK;

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

static void capture_frame(void)
{
    setup_sct_for_transducer();
    g_pulse_cycle_count = 0u;
    debug_pin_pulse(2u);
    sct_run();
    while (g_pulse_cycle_count < g_config.tx_cycles) {
        pump_uart_rx();
        __WFI();
    }
    sct_halt();

    setup_dma_for_adc();
    setup_sct_for_adc();

    g_dma_block_count = 0u;
    sct_run();
    while (g_dma_block_count < 3u) {
        pump_uart_rx();
        __WFI();
    }
    sct_halt();

    for (uint32_t i = 0u; i < ULTRASONIC_SAMPLE_COUNT; ++i) {
        g_adc_buffer[i] >>= 4u;
    }

    g_output_sample_count = ULTRASONIC_SAMPLE_COUNT;
}

static void build_envelope_frame(void)
{
    const uint16_t bias = 2048u;
    uint32_t phase_accumulator = 0u;
    uint32_t write_index = 0u;
    uint16_t current_peak = 0u;
    bool have_peak = false;

    for (uint32_t i = 0u; i < ULTRASONIC_SAMPLE_COUNT; ++i) {
        const uint16_t sample = g_adc_buffer[i];
        const uint16_t amplitude = (sample >= bias) ? (sample - bias) : (bias - sample);

        if (amplitude > current_peak) {
            current_peak = amplitude;
        }
        have_peak = true;

        phase_accumulator += g_config.tx_frequency_hz;
        if (phase_accumulator >= g_config.adc_sample_rate_hz) {
            g_adc_buffer[write_index++] = current_peak;
            current_peak = 0u;
            have_peak = false;
            while (phase_accumulator >= g_config.adc_sample_rate_hz) {
                phase_accumulator -= g_config.adc_sample_rate_hz;
            }
        }
    }

    if (have_peak && write_index < ULTRASONIC_SAMPLE_COUNT) {
        g_adc_buffer[write_index++] = current_peak;
    }

    g_output_sample_count = write_index;
}

static void emit_frame_compact(void)
{
    uart_write_byte('W');
    uart_write_byte(' ');
    for (uint32_t i = 0u; i < g_output_sample_count; ++i) {
        if ((i & 0x1Fu) == 0u) {
            pump_uart_rx();
        }
        uart_write_byte((uint8_t)(((g_adc_buffer[i] >> 6u) & 0x3Fu) + '?'));
        uart_write_byte((uint8_t)((g_adc_buffer[i] & 0x3Fu) + '?'));
    }
    uart_write_crlf();
}

static void emit_frame_text(void)
{
    uart_write_string("T seq=");
    uart_write_decimal(g_frame_sequence);
    uart_write_string(" count=");
    uart_write_decimal(g_output_sample_count);
    uart_write_byte(' ');
    for (uint32_t i = 0u; i < g_output_sample_count; ++i) {
        if ((i & 0x1Fu) == 0u) {
            pump_uart_rx();
        }
        uart_write_decimal(g_adc_buffer[i]);
        if (i + 1u < g_output_sample_count) {
            uart_write_byte(',');
        }
    }
    uart_write_crlf();
}

static void emit_frame_envelope(void)
{
    uart_write_byte('E');
    uart_write_byte(' ');
    for (uint32_t i = 0u; i < g_output_sample_count; ++i) {
        if ((i & 0x1Fu) == 0u) {
            pump_uart_rx();
        }
        uart_write_byte((uint8_t)(((g_adc_buffer[i] >> 6u) & 0x3Fu) + '?'));
        uart_write_byte((uint8_t)((g_adc_buffer[i] & 0x3Fu) + '?'));
    }
    uart_write_crlf();
}

static uint16_t crc16_ccitt_update(uint16_t crc, uint8_t data)
{
    crc ^= (uint16_t)data << 8u;
    for (uint32_t i = 0u; i < 8u; ++i) {
        if ((crc & 0x8000u) != 0u) {
            crc = (uint16_t)((crc << 1u) ^ 0x1021u);
        } else {
            crc <<= 1u;
        }
    }
    return crc;
}

static void emit_frame_binary(void)
{
    const uint16_t payload_len = (uint16_t)(((g_output_sample_count + 1u) / 2u) * 3u);
    uint16_t crc = 0xFFFFu;
    const uint8_t header[12] = {
        0x55u,
        0x57u,
        0x01u,
        0x01u,
        (uint8_t)(g_frame_sequence & 0xFFu),
        (uint8_t)((g_frame_sequence >> 8u) & 0xFFu),
        (uint8_t)((g_frame_sequence >> 16u) & 0xFFu),
        (uint8_t)((g_frame_sequence >> 24u) & 0xFFu),
        (uint8_t)(g_output_sample_count & 0xFFu),
        (uint8_t)((g_output_sample_count >> 8u) & 0xFFu),
        (uint8_t)(payload_len & 0xFFu),
        (uint8_t)((payload_len >> 8u) & 0xFFu),
    };

    uart_write_data(header, sizeof(header));
    for (uint32_t i = 0u; i < sizeof(header); ++i) {
        crc = crc16_ccitt_update(crc, header[i]);
    }

    for (uint32_t i = 0u; i < g_output_sample_count; i += 2u) {
        if ((i & 0x3Fu) == 0u) {
            pump_uart_rx();
        }
        const uint16_t sample_a = (uint16_t)(g_adc_buffer[i] & 0x0FFFu);
        const uint16_t sample_b = (uint16_t)(((i + 1u) < g_output_sample_count) ? (g_adc_buffer[i + 1u] & 0x0FFFu) : 0u);
        const uint8_t packed[3] = {
            (uint8_t)(sample_a & 0xFFu),
            (uint8_t)(((sample_a >> 8u) & 0x0Fu) | ((sample_b & 0x0Fu) << 4u)),
            (uint8_t)((sample_b >> 4u) & 0xFFu),
        };
        uart_write_data(packed, 3u);
        crc = crc16_ccitt_update(crc, packed[0]);
        crc = crc16_ccitt_update(crc, packed[1]);
        crc = crc16_ccitt_update(crc, packed[2]);
    }

    uart_write_byte((uint8_t)(crc & 0xFFu));
    uart_write_byte((uint8_t)((crc >> 8u) & 0xFFu));
}

static void emit_current_frame(void)
{
    ++g_frame_sequence;
    if (g_config.format == OUTPUT_FORMAT_ENV) {
        build_envelope_frame();
    }
    switch (g_config.format) {
    case OUTPUT_FORMAT_COMPACT:
        emit_frame_compact();
        break;
    case OUTPUT_FORMAT_TEXT:
        emit_frame_text();
        break;
    case OUTPUT_FORMAT_BIN:
        emit_frame_binary();
        break;
    case OUTPUT_FORMAT_ENV:
        emit_frame_envelope();
        break;
    default:
        emit_error("FORMAT");
        break;
    }
}

static void apply_default_configuration(void)
{
    g_config = g_default_config;
    g_continuous_active = false;
    g_pending_frames = 0u;
}

static void handle_command(const char *line)
{
    if (string_equals(line, "AT")) {
        emit_ok();
        return;
    }

    if (string_equals(line, "ATI")) {
        emit_info();
        emit_ok();
        return;
    }

    if (string_equals(line, "ATCFG?")) {
        emit_config();
        emit_ok();
        return;
    }

    if (string_equals(line, "ATMODE?")) {
        emit_query_value("MODE", mode_to_string(g_config.mode));
        emit_ok();
        return;
    }

    if (string_starts_with(line, "ATMODE=")) {
        if (capture_is_active()) {
            emit_error("BUSY");
            return;
        }
        const char *value = line + strlen("ATMODE=");
        if (string_equals(value, "SINGLE")) {
            g_config.mode = CAPTURE_MODE_SINGLE;
        } else if (string_equals(value, "NSHOT")) {
            g_config.mode = CAPTURE_MODE_NSHOT;
        } else if (string_equals(value, "CONTINUOUS")) {
            g_config.mode = CAPTURE_MODE_CONTINUOUS;
        } else {
            emit_error("BADARG");
            return;
        }
        emit_ok();
        return;
    }

    if (string_equals(line, "ATNSHOT?")) {
        emit_query_value_u32("NSHOT", g_config.nshot);
        emit_ok();
        return;
    }

    if (string_starts_with(line, "ATNSHOT=")) {
        uint32_t value;
        if (capture_is_active()) {
            emit_error("BUSY");
            return;
        }
        if (!parse_u32(line + strlen("ATNSHOT="), &value) || value == 0u) {
            emit_error("BADARG");
            return;
        }
        g_config.nshot = value;
        emit_ok();
        return;
    }

    if (string_equals(line, "ATFMT?")) {
        emit_query_value("FMT", format_to_string(g_config.format));
        emit_ok();
        return;
    }

    if (string_starts_with(line, "ATFMT=")) {
        if (capture_is_active()) {
            emit_error("BUSY");
            return;
        }
        const char *value = line + strlen("ATFMT=");
        if (string_equals(value, "COMPACT")) {
            g_config.format = OUTPUT_FORMAT_COMPACT;
        } else if (string_equals(value, "TEXT")) {
            g_config.format = OUTPUT_FORMAT_TEXT;
        } else if (string_equals(value, "BIN")) {
            g_config.format = OUTPUT_FORMAT_BIN;
        } else if (string_equals(value, "ENV")) {
            g_config.format = OUTPUT_FORMAT_ENV;
        } else {
            emit_error("BADARG");
            return;
        }
        emit_ok();
        return;
    }

    if (string_equals(line, "ATTXFREQ?")) {
        emit_query_value_u32("TXFREQ", g_config.tx_frequency_hz);
        emit_ok();
        return;
    }

    if (string_starts_with(line, "ATTXFREQ=")) {
        uint32_t value;
        if (capture_is_active()) {
            emit_error("BUSY");
            return;
        }
        if (!parse_u32(line + strlen("ATTXFREQ="), &value)) {
            emit_error("BADARG");
            return;
        }
        if (value < AT_TXFREQ_MIN_HZ || value > AT_TXFREQ_MAX_HZ) {
            emit_error("RANGE");
            return;
        }
        g_config.tx_frequency_hz = value;
        emit_ok();
        return;
    }

    if (string_equals(line, "ATTXCYCLES?")) {
        emit_query_value_u32("TXCYCLES", g_config.tx_cycles);
        emit_ok();
        return;
    }

    if (string_starts_with(line, "ATTXCYCLES=")) {
        uint32_t value;
        if (capture_is_active()) {
            emit_error("BUSY");
            return;
        }
        if (!parse_u32(line + strlen("ATTXCYCLES="), &value)) {
            emit_error("BADARG");
            return;
        }
        if (value < AT_TXCYCLES_MIN || value > AT_TXCYCLES_MAX) {
            emit_error("RANGE");
            return;
        }
        g_config.tx_cycles = value;
        emit_ok();
        return;
    }

    if (string_equals(line, "ATSRATE?")) {
        emit_query_value_u32("SRATE", g_config.adc_sample_rate_hz);
        emit_ok();
        return;
    }

    if (string_starts_with(line, "ATSRATE=")) {
        uint32_t value;
        if (capture_is_active()) {
            emit_error("BUSY");
            return;
        }
        if (!parse_u32(line + strlen("ATSRATE="), &value)) {
            emit_error("BADARG");
            return;
        }
        if (value < AT_SRATE_MIN_HZ || value > AT_SRATE_MAX_HZ) {
            emit_error("RANGE");
            return;
        }
        g_config.adc_sample_rate_hz = value;
        emit_ok();
        return;
    }

    if (string_equals(line, "ATSAMPLES?")) {
        emit_query_value_u32("SAMPLES", g_config.sample_count);
        emit_ok();
        return;
    }

    if (string_equals(line, "ATGO")) {
        if (capture_is_active()) {
            emit_error("BUSY");
            return;
        }
        switch (g_config.mode) {
        case CAPTURE_MODE_SINGLE:
            g_pending_frames = 1u;
            break;
        case CAPTURE_MODE_NSHOT:
            g_pending_frames = g_config.nshot;
            break;
        case CAPTURE_MODE_CONTINUOUS:
            g_continuous_active = true;
            break;
        default:
            emit_error("MODE");
            return;
        }
        emit_ok();
        return;
    }

    if (string_equals(line, "ATSTOP")) {
        g_continuous_active = false;
        g_pending_frames = 0u;
        emit_done_stopped();
        return;
    }

    if (string_equals(line, "ATRESET")) {
        emit_ok();
        uart_wait_tx_idle();
        __DSB();
        NVIC_SystemReset();
        for (;;) {
        }
    }

    if (string_equals(line, "ATDEFAULT")) {
        if (capture_is_active()) {
            emit_error("BUSY");
            return;
        }
        apply_default_configuration();
        emit_ok();
        return;
    }

    emit_error("UNKNOWN");
}

static void queue_completed_command(void)
{
    if (g_command_overflow) {
        g_pending_command_toolong = true;
        g_command_overflow = false;
        g_command_length = 0u;
        return;
    }

    if (g_command_length == 0u) {
        return;
    }

    g_command_buffer[g_command_length] = '\0';

    if (g_pending_command_ready) {
        g_pending_command_dropped = true;
    } else {
        memcpy(g_pending_command_buffer, g_command_buffer, g_command_length + 1u);
        g_pending_command_ready = true;
    }

    g_command_length = 0u;
}

static void pump_uart_rx(void)
{
    while (uart_rx_ready()) {
        const char byte = (char)uart_read_byte();

        if (byte == '\r') {
            continue;
        }

        if (byte == '\n') {
            queue_completed_command();
            continue;
        }

        if (g_command_length + 1u >= AT_COMMAND_BUFFER_SIZE) {
            g_command_overflow = true;
            continue;
        }

        g_command_buffer[g_command_length++] = byte;
    }
}

static void service_pending_command(void)
{
    if (g_pending_command_toolong) {
        g_pending_command_toolong = false;
        emit_error("TOOLONG");
    }

    if (g_pending_command_dropped) {
        g_pending_command_dropped = false;
        emit_error("BUSY");
    }

    if (g_pending_command_ready) {
        g_pending_command_ready = false;
        handle_command(g_pending_command_buffer);
    }
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
    adc_init();

    emit_info();
    emit_config();

    while (1) {
        pump_uart_rx();
        service_pending_command();

        if (!capture_is_active()) {
            continue;
        }

        capture_frame();
        emit_current_frame();
        pump_uart_rx();
        service_pending_command();

        if (g_pending_frames > 0u) {
            --g_pending_frames;
            if (g_pending_frames == 0u && g_config.mode != CAPTURE_MODE_CONTINUOUS) {
                emit_done_frames((g_config.mode == CAPTURE_MODE_SINGLE) ? 1u : g_config.nshot);
            }
        }
    }
}
