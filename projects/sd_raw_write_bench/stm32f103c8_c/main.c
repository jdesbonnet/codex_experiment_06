#include <stdbool.h>
#include <stdint.h>

#include "stm32f103xb.h"

/*
 * STM32F103C8 raw SD write benchmark using a host-preallocated contiguous
 * file region. The host prepared CODXLOG.BIN on the FAT boot partition and
 * resolved its extent to:
 *
 *   start_lba    = 13053
 *   sector_count = 16384
 *
 * This lets the MCU measure realistic logging throughput without carrying FAT
 * code in the write path.
 *
 * References:
 * - ST RM0008 for SPI1 / GPIO / USART1 / RCC programming.
 * - SanDisk OEM product manual for SPI command framing.
 * - Elm-Chan MMC/SDC SPI-mode note for init and multi-block write flow.
 */

#define UART_BAUD 57600u

#define SD_CMD0   0u
#define SD_CMD8   8u
#define SD_CMD16  16u
#define SD_CMD17  17u
#define SD_CMD24  24u
#define SD_CMD25  25u
#define SD_CMD55  55u
#define SD_CMD58  58u
#define SD_ACMD23 23u
#define SD_ACMD41 41u

#define SD_R1_IDLE       0x01u
#define SD_R1_ILLEGAL    0x04u
#define SD_DATA_TOKEN    0xFEu
#define SD_MULTI_TOKEN   0xFCu
#define SD_STOP_TOKEN    0xFDu
#define SD_DATA_ACCEPTED 0x05u
#define SD_SECTOR_SIZE   512u

#define SD_SPI_BR_INIT (SPI_CR1_BR_2 | SPI_CR1_BR_1)

#ifndef SD_SPI_BENCH_DIV
#define SD_SPI_BENCH_DIV 8u
#endif

#ifndef STM32_BENCH_SYSCLK_HZ
#define STM32_BENCH_SYSCLK_HZ 8000000u
#endif

#if SD_SPI_BENCH_DIV == 2
#define SD_SPI_BR_RUN 0u
#elif SD_SPI_BENCH_DIV == 4
#define SD_SPI_BR_RUN SPI_CR1_BR_0
#elif SD_SPI_BENCH_DIV == 8
#define SD_SPI_BR_RUN SPI_CR1_BR_1
#elif SD_SPI_BENCH_DIV == 16
#define SD_SPI_BR_RUN (SPI_CR1_BR_1 | SPI_CR1_BR_0)
#elif SD_SPI_BENCH_DIV == 32
#define SD_SPI_BR_RUN SPI_CR1_BR_2
#elif SD_SPI_BENCH_DIV == 64
#define SD_SPI_BR_RUN (SPI_CR1_BR_2 | SPI_CR1_BR_0)
#elif SD_SPI_BENCH_DIV == 128
#define SD_SPI_BR_RUN (SPI_CR1_BR_2 | SPI_CR1_BR_1)
#elif SD_SPI_BENCH_DIV == 256
#define SD_SPI_BR_RUN (SPI_CR1_BR_2 | SPI_CR1_BR_1 | SPI_CR1_BR_0)
#else
#error "Unsupported SD_SPI_BENCH_DIV value"
#endif

#if STM32_BENCH_SYSCLK_HZ == 8000000u
#define STM32_BENCH_PLL_MUL_BITS 0u
#elif STM32_BENCH_SYSCLK_HZ == 64000000u
#define STM32_BENCH_PLL_MUL_BITS RCC_CFGR_PLLMULL16
#else
#error "Unsupported STM32_BENCH_SYSCLK_HZ value"
#endif

#define SD_SPI_BENCH_HZ (SystemCoreClock / SD_SPI_BENCH_DIV)

#define RAW_REGION_START_LBA    13053u
#define RAW_REGION_SECTOR_COUNT 16384u

#ifndef SD_WRITE_BENCH_BYTES
#define SD_WRITE_BENCH_BYTES (256u * 1024u)
#endif

#define BENCH_TOTAL_BYTES    SD_WRITE_BENCH_BYTES
#define BENCH_BUFFER_SIZE    4096u
#define BENCH_SECTORS_TOTAL  (BENCH_TOTAL_BYTES / SD_SECTOR_SIZE)
#define BENCH_CHUNK_SECTORS  (BENCH_BUFFER_SIZE / SD_SECTOR_SIZE)
#define BENCH_PROGRESS_BYTES (16u * 1024u)

#define PATTERN_MAGIC0 'C'
#define PATTERN_MAGIC1 'D'
#define PATTERN_MAGIC2 'X'
#define PATTERN_MAGIC3 '1'

static volatile uint32_t g_ms_ticks;

static bool g_sd_is_sdhc;
static uint32_t g_sd_sector_count;
static uint8_t g_bench_buffer[BENCH_BUFFER_SIZE];
static uint8_t g_verify_buffer[SD_SECTOR_SIZE];

void SysTick_Handler(void)
{
    g_ms_ticks++;
}

static void delay_ms(uint32_t delay_ms)
{
    uint32_t start = g_ms_ticks;
    while ((uint32_t)(g_ms_ticks - start) < delay_ms) {
        /* Busy wait. */
    }
}

static void usart1_putc(char ch)
{
    while ((USART1->SR & USART_SR_TXE) == 0u) {
        /* Wait for TX space. */
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

static void usart1_put_hex16(uint16_t value)
{
    usart1_put_hex8((uint8_t)(value >> 8));
    usart1_put_hex8((uint8_t)value);
}

static void usart1_put_hex32(uint32_t value)
{
    usart1_put_hex16((uint16_t)(value >> 16));
    usart1_put_hex16((uint16_t)value);
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

static void usart1_put_dec_tenths_u32(uint32_t value_x10)
{
    usart1_put_dec_u32(value_x10 / 10u);
    usart1_putc('.');
    usart1_putc((char)('0' + (value_x10 % 10u)));
}

static void usart1_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPAEN | RCC_APB2ENR_USART1EN;
    AFIO->MAPR &= ~AFIO_MAPR_USART1_REMAP;

    GPIOA->CRH &= ~(GPIO_CRH_MODE9 | GPIO_CRH_CNF9 | GPIO_CRH_MODE10 | GPIO_CRH_CNF10);
    GPIOA->CRH |= GPIO_CRH_MODE9 | GPIO_CRH_CNF9_1 | GPIO_CRH_CNF10_0;

    USART1->CR1 = 0u;
    USART1->BRR = (SystemCoreClock + (UART_BAUD / 2u)) / UART_BAUD;
    USART1->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

static void led_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_IOPCEN;
    GPIOC->CRH &= ~(GPIO_CRH_MODE13 | GPIO_CRH_CNF13);
    GPIOC->CRH |= GPIO_CRH_MODE13_1;
    GPIOC->BSRR = GPIO_BSRR_BS13;
}

static void led_set(bool on)
{
    if (on) {
        GPIOC->BRR = GPIO_BRR_BR13;
    } else {
        GPIOC->BSRR = GPIO_BSRR_BS13;
    }
}

static void system_clock_config(void)
{
#if STM32_BENCH_SYSCLK_HZ == 64000000u
    RCC->CR |= RCC_CR_HSION;
    while ((RCC->CR & RCC_CR_HSIRDY) == 0u) {
        /* Wait for HSI ready. */
    }

    FLASH->ACR = FLASH_ACR_PRFTBE | FLASH_ACR_LATENCY_2;

    RCC->CFGR &= ~(RCC_CFGR_HPRE |
                   RCC_CFGR_PPRE1 |
                   RCC_CFGR_PPRE2 |
                   RCC_CFGR_SW |
                   RCC_CFGR_PLLSRC |
                   RCC_CFGR_PLLXTPRE |
                   RCC_CFGR_PLLMULL);
    RCC->CFGR |= RCC_CFGR_HPRE_DIV1 |
                 RCC_CFGR_PPRE2_DIV1 |
                 RCC_CFGR_PPRE1_DIV2 |
                 STM32_BENCH_PLL_MUL_BITS;

    RCC->CR &= ~RCC_CR_PLLON;
    RCC->CR |= RCC_CR_PLLON;
    while ((RCC->CR & RCC_CR_PLLRDY) == 0u) {
        /* Wait for PLL lock. */
    }

    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_SW) | RCC_CFGR_SW_PLL;
    while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_PLL) {
        /* Wait for PLL system clock switch. */
    }
#endif

    SystemCoreClockUpdate();
}

static void sd_spi_set_prescaler(uint32_t br)
{
    SPI1->CR1 &= ~SPI_CR1_SPE;
    SPI1->CR1 = (SPI1->CR1 & ~SPI_CR1_BR) | br;
    SPI1->CR1 |= SPI_CR1_SPE;
}

static void sd_spi_init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPAEN | RCC_APB2ENR_SPI1EN;
    AFIO->MAPR &= ~AFIO_MAPR_SPI1_REMAP;

    GPIOA->CRL &= ~(GPIO_CRL_MODE4 | GPIO_CRL_CNF4 |
                    GPIO_CRL_MODE5 | GPIO_CRL_CNF5 |
                    GPIO_CRL_MODE6 | GPIO_CRL_CNF6 |
                    GPIO_CRL_MODE7 | GPIO_CRL_CNF7);
    GPIOA->CRL |= GPIO_CRL_MODE4_0 |
                  GPIO_CRL_MODE5 | GPIO_CRL_CNF5_1 |
                  GPIO_CRL_CNF6_0 |
                  GPIO_CRL_MODE7 | GPIO_CRL_CNF7_1;

    GPIOA->BSRR = GPIO_BSRR_BS4;

    SPI1->CR1 = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI | SD_SPI_BR_INIT;
    SPI1->CR2 = 0u;
    SPI1->CR1 |= SPI_CR1_SPE;
}

static inline void sd_cs_high(void)
{
    GPIOA->BSRR = GPIO_BSRR_BS4;
}

static inline void sd_cs_low(void)
{
    GPIOA->BRR = GPIO_BRR_BR4;
}

static uint8_t sd_spi_xfer(uint8_t tx)
{
    while ((SPI1->SR & SPI_SR_TXE) == 0u) {
        /* Wait for TX buffer availability. */
    }

    *(__IO uint8_t *)&SPI1->DR = tx;

    while ((SPI1->SR & SPI_SR_RXNE) == 0u) {
        /* Wait for RX data. */
    }

    return *(__IO uint8_t *)&SPI1->DR;
}

static void sd_deselect(void)
{
    sd_cs_high();
    sd_spi_xfer(0xFFu);
}

static bool sd_wait_ready(uint32_t timeout_bytes)
{
    uint32_t i;

    for (i = 0u; i < timeout_bytes; i++) {
        if (sd_spi_xfer(0xFFu) == 0xFFu) {
            return true;
        }
    }

    return false;
}

static bool sd_select(void)
{
    sd_cs_low();
    return sd_wait_ready(50000u);
}

static void sd_send_initial_clocks(void)
{
    uint32_t i;

    sd_deselect();
    for (i = 0u; i < 10u; i++) {
        sd_spi_xfer(0xFFu);
    }
}

static uint8_t sd_send_command_selected(uint8_t cmd, uint32_t arg, uint8_t crc)
{
    uint8_t r1 = 0xFFu;
    uint32_t i;

    sd_spi_xfer((uint8_t)(0x40u | cmd));
    sd_spi_xfer((uint8_t)(arg >> 24));
    sd_spi_xfer((uint8_t)(arg >> 16));
    sd_spi_xfer((uint8_t)(arg >> 8));
    sd_spi_xfer((uint8_t)arg);
    sd_spi_xfer(crc);

    for (i = 0u; i < 10u; i++) {
        r1 = sd_spi_xfer(0xFFu);
        if ((r1 & 0x80u) == 0u) {
            break;
        }
    }

    return r1;
}

static uint8_t sd_send_command(uint8_t cmd, uint32_t arg, uint8_t crc)
{
    uint8_t r1;

    sd_deselect();
    if (!sd_select()) {
        sd_deselect();
        return 0xFFu;
    }

    r1 = sd_send_command_selected(cmd, arg, crc);
    sd_deselect();
    return r1;
}

static uint8_t sd_send_app_command(uint8_t acmd, uint32_t arg)
{
    uint8_t r1 = sd_send_command(SD_CMD55, 0u, 0xFFu);
    if (r1 > 0x01u) {
        return r1;
    }
    return sd_send_command(acmd, arg, 0xFFu);
}

static bool sd_read_data_selected(uint8_t *buffer, uint32_t length)
{
    uint32_t i;
    uint8_t token = 0xFFu;

    for (i = 0u; i < 100000u; i++) {
        token = sd_spi_xfer(0xFFu);
        if (token != 0xFFu) {
            break;
        }
    }

    if (token != SD_DATA_TOKEN) {
        return false;
    }

    for (i = 0u; i < length; i++) {
        buffer[i] = sd_spi_xfer(0xFFu);
    }

    sd_spi_xfer(0xFFu);
    sd_spi_xfer(0xFFu);
    return true;
}

static bool sd_read_ocr(uint32_t *ocr_out)
{
    uint8_t r1;
    uint8_t ocr[4];

    sd_deselect();
    if (!sd_select()) {
        sd_deselect();
        return false;
    }

    r1 = sd_send_command_selected(SD_CMD58, 0u, 0xFFu);
    if (r1 != 0x00u && r1 != SD_R1_IDLE) {
        sd_deselect();
        return false;
    }

    ocr[0] = sd_spi_xfer(0xFFu);
    ocr[1] = sd_spi_xfer(0xFFu);
    ocr[2] = sd_spi_xfer(0xFFu);
    ocr[3] = sd_spi_xfer(0xFFu);
    sd_deselect();

    *ocr_out = ((uint32_t)ocr[0] << 24) |
               ((uint32_t)ocr[1] << 16) |
               ((uint32_t)ocr[2] << 8) |
               (uint32_t)ocr[3];
    return true;
}

static bool sd_read_block(uint32_t lba, uint8_t *buffer)
{
    uint32_t address = g_sd_is_sdhc ? lba : (lba * SD_SECTOR_SIZE);
    uint8_t r1;

    sd_deselect();
    if (!sd_select()) {
        sd_deselect();
        return false;
    }

    r1 = sd_send_command_selected(SD_CMD17, address, 0xFFu);
    if (r1 != 0x00u) {
        sd_deselect();
        return false;
    }

    if (!sd_read_data_selected(buffer, SD_SECTOR_SIZE)) {
        sd_deselect();
        return false;
    }

    sd_deselect();
    return true;
}

static bool sd_write_data_selected(const uint8_t *buffer, uint8_t token)
{
    uint32_t i;
    uint8_t response;

    sd_spi_xfer(0xFFu);
    sd_spi_xfer(token);

    for (i = 0u; i < SD_SECTOR_SIZE; i++) {
        sd_spi_xfer(buffer[i]);
    }

    sd_spi_xfer(0xFFu);
    sd_spi_xfer(0xFFu);

    response = sd_spi_xfer(0xFFu) & 0x1Fu;
    if (response != SD_DATA_ACCEPTED) {
        return false;
    }

    return sd_wait_ready(400000u);
}

static bool sd_write_block(uint32_t lba, const uint8_t *buffer)
{
    uint32_t address = g_sd_is_sdhc ? lba : (lba * SD_SECTOR_SIZE);
    uint8_t r1;

    sd_deselect();
    if (!sd_select()) {
        sd_deselect();
        return false;
    }

    r1 = sd_send_command_selected(SD_CMD24, address, 0xFFu);
    if (r1 != 0x00u) {
        sd_deselect();
        return false;
    }

    if (!sd_write_data_selected(buffer, SD_DATA_TOKEN)) {
        sd_deselect();
        return false;
    }

    sd_deselect();
    return true;
}

static bool sd_write_blocks_multi(uint32_t lba, const uint8_t *buffer, uint32_t sector_count)
{
    uint32_t address = g_sd_is_sdhc ? lba : (lba * SD_SECTOR_SIZE);
    uint32_t i;
    uint8_t r1;

    /*
     * ACMD23 is optional but can help some cards prepare internal erase/program
     * handling for an upcoming multi-block write.
     */
    (void)sd_send_app_command(SD_ACMD23, sector_count);

    sd_deselect();
    if (!sd_select()) {
        sd_deselect();
        return false;
    }

    r1 = sd_send_command_selected(SD_CMD25, address, 0xFFu);
    if (r1 != 0x00u) {
        sd_deselect();
        return false;
    }

    for (i = 0u; i < sector_count; i++) {
        if (!sd_write_data_selected(buffer + (i * SD_SECTOR_SIZE), SD_MULTI_TOKEN)) {
            sd_deselect();
            return false;
        }
    }

    sd_spi_xfer(0xFFu);
    sd_spi_xfer(SD_STOP_TOKEN);
    if (!sd_wait_ready(400000u)) {
        sd_deselect();
        return false;
    }

    sd_deselect();
    return true;
}

static uint32_t sd_extract_bits(const uint8_t *data, uint8_t msb, uint8_t lsb)
{
    uint32_t value = 0u;
    uint8_t bit;

    for (bit = msb; bit >= lsb; bit--) {
        uint8_t byte_index = (uint8_t)(15u - (bit / 8u));
        uint8_t bit_index = (uint8_t)(bit & 7u);
        value <<= 1;
        value |= (uint32_t)((data[byte_index] >> bit_index) & 1u);
        if (bit == lsb) {
            break;
        }
    }

    return value;
}

static uint32_t sd_csd_sector_count(const uint8_t *csd)
{
    uint32_t csd_structure = sd_extract_bits(csd, 127u, 126u);

    if (csd_structure == 1u) {
        uint32_t c_size = sd_extract_bits(csd, 69u, 48u);
        return (c_size + 1u) * 1024u;
    }

    if (csd_structure == 0u) {
        uint32_t read_bl_len = sd_extract_bits(csd, 83u, 80u);
        uint32_t c_size = sd_extract_bits(csd, 73u, 62u);
        uint32_t c_size_mult = sd_extract_bits(csd, 49u, 47u);
        uint32_t block_len = 1u << read_bl_len;
        uint32_t blocknr = (c_size + 1u) * (1u << (c_size_mult + 2u));
        return (blocknr * block_len) / SD_SECTOR_SIZE;
    }

    return 0u;
}

static bool sd_card_init(void)
{
    uint32_t i;
    uint8_t r1;
    uint8_t r7[4];
    uint8_t csd[16];
    uint32_t ocr = 0u;

    g_sd_is_sdhc = false;
    g_sd_sector_count = 0u;

    sd_send_initial_clocks();

    usart1_puts("sd: CMD0...\r\n");
    for (i = 0u; i < 20u; i++) {
        r1 = sd_send_command(SD_CMD0, 0u, 0x95u);
        if (r1 == SD_R1_IDLE) {
            break;
        }
    }
    usart1_puts("sd: CMD0 R1=0x");
    usart1_put_hex8(r1);
    usart1_puts("\r\n");
    if (r1 != SD_R1_IDLE) {
        return false;
    }

    sd_deselect();
    if (!sd_select()) {
        sd_deselect();
        return false;
    }
    r1 = sd_send_command_selected(SD_CMD8, 0x000001AAu, 0x87u);
    r7[0] = sd_spi_xfer(0xFFu);
    r7[1] = sd_spi_xfer(0xFFu);
    r7[2] = sd_spi_xfer(0xFFu);
    r7[3] = sd_spi_xfer(0xFFu);
    sd_deselect();

    usart1_puts("sd: CMD8 R1=0x");
    usart1_put_hex8(r1);
    usart1_puts(" R7=");
    usart1_put_hex8(r7[0]);
    usart1_putc(' ');
    usart1_put_hex8(r7[1]);
    usart1_putc(' ');
    usart1_put_hex8(r7[2]);
    usart1_putc(' ');
    usart1_put_hex8(r7[3]);
    usart1_puts("\r\n");

    if ((r1 & SD_R1_ILLEGAL) == 0u) {
        for (i = 0u; i < 1000u; i++) {
            r1 = sd_send_app_command(SD_ACMD41, 0x40000000u);
            if (r1 == 0x00u) {
                break;
            }
        }
        usart1_puts("sd: ACMD41(v2) polls=");
        usart1_put_dec_u32(i + 1u);
        usart1_puts(" R1=0x");
        usart1_put_hex8(r1);
        usart1_puts("\r\n");
        if (r1 != 0x00u) {
            return false;
        }
    } else {
        for (i = 0u; i < 1000u; i++) {
            r1 = sd_send_app_command(SD_ACMD41, 0u);
            if (r1 == 0x00u) {
                break;
            }
        }
        usart1_puts("sd: ACMD41(v1) polls=");
        usart1_put_dec_u32(i + 1u);
        usart1_puts(" R1=0x");
        usart1_put_hex8(r1);
        usart1_puts("\r\n");
        if (r1 != 0x00u) {
            return false;
        }
    }

    if (!sd_read_ocr(&ocr)) {
        return false;
    }
    g_sd_is_sdhc = ((ocr & 0x40000000u) != 0u);

    usart1_puts("sd: OCR=0x");
    usart1_put_hex32(ocr);
    usart1_puts(" type=");
    usart1_puts(g_sd_is_sdhc ? "SDHC/SDXC" : "SDSC");
    usart1_puts("\r\n");

    if (!g_sd_is_sdhc) {
        r1 = sd_send_command(SD_CMD16, SD_SECTOR_SIZE, 0xFFu);
        usart1_puts("sd: CMD16 R1=0x");
        usart1_put_hex8(r1);
        usart1_puts("\r\n");
        if (r1 != 0x00u) {
            return false;
        }
    }

    sd_deselect();
    if (!sd_select()) {
        sd_deselect();
        return false;
    }
    r1 = sd_send_command_selected(SD_CMD17, g_sd_is_sdhc ? 0u : 0u, 0xFFu);
    if (r1 != 0x00u) {
        sd_deselect();
        return false;
    }
    if (!sd_read_data_selected(g_verify_buffer, SD_SECTOR_SIZE)) {
        sd_deselect();
        return false;
    }
    sd_deselect();

    /* Read CSD after init so we can report total sectors. */
    sd_deselect();
    if (!sd_select()) {
        sd_deselect();
        return false;
    }
    r1 = sd_send_command_selected(9u, 0u, 0xFFu);
    if (r1 != 0x00u && r1 != SD_R1_IDLE) {
        sd_deselect();
        return false;
    }
    if (!sd_read_data_selected(csd, 16u)) {
        sd_deselect();
        return false;
    }
    sd_deselect();

    g_sd_sector_count = sd_csd_sector_count(csd);
    usart1_puts("sd: sectors=");
    usart1_put_dec_u32(g_sd_sector_count);
    usart1_puts(" capacity_mib=");
    usart1_put_dec_u32(g_sd_sector_count / 2048u);
    usart1_puts("\r\n");

    sd_spi_set_prescaler(SD_SPI_BR_RUN);
    return true;
}

static void fill_pattern_sector(uint8_t *dst, uint32_t absolute_lba)
{
    uint32_t i;

    dst[0] = (uint8_t)PATTERN_MAGIC0;
    dst[1] = (uint8_t)PATTERN_MAGIC1;
    dst[2] = (uint8_t)PATTERN_MAGIC2;
    dst[3] = (uint8_t)PATTERN_MAGIC3;
    dst[4] = (uint8_t)(absolute_lba);
    dst[5] = (uint8_t)(absolute_lba >> 8);
    dst[6] = (uint8_t)(absolute_lba >> 16);
    dst[7] = (uint8_t)(absolute_lba >> 24);

    for (i = 8u; i < SD_SECTOR_SIZE; i++) {
        dst[i] = (uint8_t)(absolute_lba + i);
    }
}

static void fill_bench_buffer(uint32_t first_lba, uint32_t sector_count)
{
    uint32_t i;

    for (i = 0u; i < sector_count; i++) {
        fill_pattern_sector(g_bench_buffer + (i * SD_SECTOR_SIZE), first_lba + i);
    }
}

static bool verify_sector_pattern(uint32_t lba)
{
    uint8_t expected[SD_SECTOR_SIZE];
    uint32_t i;

    fill_pattern_sector(expected, lba);
    if (!sd_read_block(lba, g_verify_buffer)) {
        return false;
    }

    for (i = 0u; i < SD_SECTOR_SIZE; i++) {
        if (g_verify_buffer[i] != expected[i]) {
            return false;
        }
    }

    return true;
}

static void run_raw_benchmark(bool multi_block)
{
    uint32_t bytes_remaining = BENCH_TOTAL_BYTES;
    uint32_t bytes_total = 0u;
    uint32_t lba = RAW_REGION_START_LBA;
    uint32_t next_progress = BENCH_PROGRESS_BYTES;
    uint32_t t0;
    uint32_t t1;
    uint32_t t2;
    uint32_t sector_count;
    bool ok = true;
    bool first_ok;
    bool last_ok;

    if (BENCH_SECTORS_TOTAL > RAW_REGION_SECTOR_COUNT) {
        usart1_puts("rawbench: requested byte count exceeds reserved region\r\n");
        return;
    }

    usart1_puts("rawbench: mode=");
    usart1_puts(multi_block ? "multi" : "single");
    usart1_puts(" start_lba=");
    usart1_put_dec_u32(RAW_REGION_START_LBA);
    usart1_puts(" region_sectors=");
    usart1_put_dec_u32(RAW_REGION_SECTOR_COUNT);
    usart1_puts(" bytes=");
    usart1_put_dec_u32(BENCH_TOTAL_BYTES);
    usart1_puts(" chunk=");
    usart1_put_dec_u32(BENCH_BUFFER_SIZE);
    usart1_puts(" spi_prescaler=/");
    usart1_put_dec_u32(SD_SPI_BENCH_DIV);
    usart1_puts(" spi_hz=");
    usart1_put_dec_u32(SD_SPI_BENCH_HZ);
    usart1_puts("\r\n");

    t0 = g_ms_ticks;
    while (bytes_remaining > 0u) {
        sector_count = bytes_remaining / SD_SECTOR_SIZE;
        if (sector_count > BENCH_CHUNK_SECTORS) {
            sector_count = BENCH_CHUNK_SECTORS;
        }

        fill_bench_buffer(lba, sector_count);

        if (multi_block) {
            ok = sd_write_blocks_multi(lba, g_bench_buffer, sector_count);
        } else {
            uint32_t i;
            for (i = 0u; i < sector_count; i++) {
                if (!sd_write_block(lba + i, g_bench_buffer + (i * SD_SECTOR_SIZE))) {
                    ok = false;
                    break;
                }
            }
        }

        if (!ok) {
            usart1_puts("rawbench: mode=");
            usart1_puts(multi_block ? "multi" : "single");
            usart1_puts(" write_error at lba=");
            usart1_put_dec_u32(lba);
            usart1_puts("\r\n");
            return;
        }

        lba += sector_count;
        bytes_total += sector_count * SD_SECTOR_SIZE;
        bytes_remaining -= sector_count * SD_SECTOR_SIZE;

        if (bytes_total >= next_progress || bytes_remaining == 0u) {
            usart1_puts("rawbench: mode=");
            usart1_puts(multi_block ? "multi" : "single");
            usart1_puts(" progress_bytes=");
            usart1_put_dec_u32(bytes_total);
            usart1_puts(" elapsed_ms=");
            usart1_put_dec_u32(g_ms_ticks - t0);
            usart1_puts("\r\n");
            next_progress += BENCH_PROGRESS_BYTES;
        }
    }
    t1 = g_ms_ticks;

    first_ok = verify_sector_pattern(RAW_REGION_START_LBA);
    last_ok = verify_sector_pattern(RAW_REGION_START_LBA + BENCH_SECTORS_TOTAL - 1u);
    t2 = g_ms_ticks;

    usart1_puts("rawbench: mode=");
    usart1_puts(multi_block ? "multi" : "single");
    usart1_puts(" bytes_written=");
    usart1_put_dec_u32(bytes_total);
    usart1_puts("\r\n");

    usart1_puts("rawbench: mode=");
    usart1_puts(multi_block ? "multi" : "single");
    usart1_puts(" write_ms=");
    usart1_put_dec_u32(t1 - t0);
    usart1_puts(" verify_ms=");
    usart1_put_dec_u32(t2 - t1);
    usart1_puts(" total_ms=");
    usart1_put_dec_u32(t2 - t0);
    usart1_puts("\r\n");

    usart1_puts("rawbench: mode=");
    usart1_puts(multi_block ? "multi" : "single");
    usart1_puts(" write_rate_kBps=");
    if ((t1 - t0) == 0u) {
        usart1_puts("0.0");
    } else {
        usart1_put_dec_tenths_u32((bytes_total * 10u) / (t1 - t0));
    }
    usart1_puts(" total_rate_kBps=");
    if ((t2 - t0) == 0u) {
        usart1_puts("0.0");
    } else {
        usart1_put_dec_tenths_u32((bytes_total * 10u) / (t2 - t0));
    }
    usart1_puts("\r\n");

    usart1_puts("rawbench: mode=");
    usart1_puts(multi_block ? "multi" : "single");
    usart1_puts(" verify_first=");
    usart1_puts(first_ok ? "OK" : "FAIL");
    usart1_puts(" verify_last=");
    usart1_puts(last_ok ? "OK" : "FAIL");
    usart1_puts("\r\n");
}

int main(void)
{
    system_clock_config();
    SysTick_Config(SystemCoreClock / 1000u);
    led_init();
    usart1_init();
    sd_spi_init();

    usart1_puts("\r\nsd_raw_write_bench: STM32F103C8 SPI1 / USART1\r\n");
    usart1_puts("sd_raw_write_bench: raw write benchmark into contiguous file region\r\n");
    usart1_puts("sd_raw_write_bench: PA4=CS PA5=SCK PA6=MISO PA7=MOSI\r\n");
    usart1_puts("sd_raw_write_bench: sysclk_hz=");
    usart1_put_dec_u32(SystemCoreClock);
    usart1_puts("\r\n");
    usart1_puts("sd_raw_write_bench: starting in 1000 ms\r\n");
    delay_ms(1000u);

    led_set(true);

    if (!sd_card_init()) {
        usart1_puts("sd_raw_write_bench: init failed\r\n");
        led_set(false);
        while (1) {
            delay_ms(1000u);
        }
    }

    run_raw_benchmark(false);
    run_raw_benchmark(true);

    usart1_puts("sd_raw_write_bench: complete\r\n");
    led_set(false);

    while (1) {
        delay_ms(1000u);
    }
}
