#include <stdbool.h>
#include <stdint.h>

#include "stm32f103xb.h"

/*
 * SD card SPI-mode bring-up for STM32F103C8.
 *
 * References:
 * - ST RM0008 for SPI1 / GPIO / USART1 register programming.
 * - SanDisk OEM product manual for SPI command framing and register layouts.
 * - Elm-Chan MMC/SDC app note for practical SPI-mode initialization flow.
 *
 * Wiring:
 *   PA4  = SD CS   (card pin 1 / DAT3)
 *   PA5  = SD SCK  (card pin 5 / CLK)
 *   PA6  = SD MISO (card pin 7 / DAT0)
 *   PA7  = SD MOSI (card pin 2 / CMD)
 *   PA9  = USART1 TX
 *   PA10 = USART1 RX
 */

#define UART_BAUD 57600u

#define SD_CMD0   0u
#define SD_CMD8   8u
#define SD_CMD9   9u
#define SD_CMD10  10u
#define SD_CMD16  16u
#define SD_CMD17  17u
#define SD_CMD55  55u
#define SD_CMD58  58u
#define SD_ACMD41 41u

#define SD_R1_IDLE       0x01u
#define SD_R1_ILLEGAL    0x04u
#define SD_DATA_TOKEN    0xFEu
#define SD_SECTOR_SIZE   512u

#define SD_SPI_BR_INIT   (SPI_CR1_BR_2 | SPI_CR1_BR_1) /* PCLK/128 = 62.5 kHz at 8 MHz */
#define SD_SPI_BR_RUN    (SPI_CR1_BR_1)                /* PCLK/8 = 1 MHz at 8 MHz */

static volatile uint32_t g_ms_ticks;

static bool g_sd_is_sdhc;
static uint8_t g_sector0[SD_SECTOR_SIZE];

typedef struct {
    uint8_t boot;
    uint8_t type;
    uint32_t start_lba;
    uint32_t sector_count;
} sd_partition_t;

void SysTick_Handler(void)
{
    g_ms_ticks++;
}

static void delay_ms(uint32_t delay_ms)
{
    uint32_t start = g_ms_ticks;
    while ((uint32_t)(g_ms_ticks - start) < delay_ms) {
        /* Busy wait; timing accuracy is not critical here. */
    }
}

static void usart1_putc(char ch)
{
    while ((USART1->SR & USART_SR_TXE) == 0u) {
        /* Wait for TX holding register space. */
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

    /*
     * PA4  = GPIO output push-pull for CS
     * PA5  = alternate-function push-pull for SCK
     * PA6  = floating input for MISO
     * PA7  = alternate-function push-pull for MOSI
     */
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
        /* Wait for a received byte. */
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

    /* Ignore the 16-bit CRC for now. */
    sd_spi_xfer(0xFFu);
    sd_spi_xfer(0xFFu);
    return true;
}

static bool sd_read_register(uint8_t cmd, uint8_t *buffer)
{
    uint8_t r1;

    sd_deselect();
    if (!sd_select()) {
        sd_deselect();
        return false;
    }

    r1 = sd_send_command_selected(cmd, 0u, 0xFFu);
    if (r1 != 0x00u && r1 != SD_R1_IDLE) {
        sd_deselect();
        return false;
    }

    if (!sd_read_data_selected(buffer, 16u)) {
        sd_deselect();
        return false;
    }

    sd_deselect();
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

static void sd_print_bytes(const uint8_t *data, uint32_t length)
{
    uint32_t i;

    for (i = 0u; i < length; i++) {
        if (i != 0u) {
            usart1_putc(' ');
        }
        usart1_put_hex8(data[i]);
    }
    usart1_puts("\r\n");
}

static bool sector_has_string(const uint8_t *sector, uint32_t offset, const char *text, uint32_t length)
{
    uint32_t i;

    for (i = 0u; i < length; i++) {
        if (sector[offset + i] != (uint8_t)text[i]) {
            return false;
        }
    }

    return true;
}

static uint16_t read_le16(const uint8_t *p)
{
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint32_t read_le32(const uint8_t *p)
{
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint64_t read_le64(const uint8_t *p)
{
    return (uint64_t)read_le32(p) | ((uint64_t)read_le32(p + 4) << 32);
}

static bool sd_is_exfat_boot_sector(const uint8_t *sector)
{
    return sector_has_string(sector, 3u, "EXFAT   ", 8u);
}

static bool sd_is_fat32_boot_sector(const uint8_t *sector)
{
    return sector_has_string(sector, 82u, "FAT32   ", 8u);
}

static bool sd_is_fat12_or_fat16_boot_sector(const uint8_t *sector)
{
    return sector_has_string(sector, 54u, "FAT12   ", 8u) ||
           sector_has_string(sector, 54u, "FAT16   ", 8u);
}

static void usart1_put_dec_u64(uint64_t value)
{
    char buffer[20];
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

static void sd_print_sector_prefix(const uint8_t *sector)
{
    uint32_t offset;
    uint32_t i;

    for (offset = 0u; offset < 32u; offset += 16u) {
        usart1_puts("sd: sector0 ");
        usart1_put_hex16((uint16_t)offset);
        usart1_puts(": ");
        for (i = 0u; i < 16u; i++) {
            if (i != 0u) {
                usart1_putc(' ');
            }
            usart1_put_hex8(sector[offset + i]);
        }
        usart1_puts("\r\n");
    }
}

static bool sd_partition_type_is_fat_like(uint8_t type)
{
    switch (type) {
    case 0x01u:
    case 0x04u:
    case 0x06u:
    case 0x0Bu:
    case 0x0Cu:
    case 0x0Eu:
    case 0x07u:
        return true;
    default:
        return false;
    }
}

static void sd_parse_partition_entry(const uint8_t *entry, sd_partition_t *part)
{
    part->boot = entry[0];
    part->type = entry[4];
    part->start_lba = read_le32(entry + 8);
    part->sector_count = read_le32(entry + 12);
}

static void sd_print_partition_entry(uint32_t index, const sd_partition_t *part)
{

    usart1_puts("sd: part");
    usart1_put_dec_u32(index);
    usart1_puts(" boot=0x");
    usart1_put_hex8(part->boot);
    usart1_puts(" type=0x");
    usart1_put_hex8(part->type);
    usart1_puts(" start_lba=");
    usart1_put_dec_u32(part->start_lba);
    usart1_puts(" sectors=");
    usart1_put_dec_u32(part->sector_count);
    usart1_puts("\r\n");
}

static bool sd_find_primary_volume(const uint8_t *mbr, uint32_t *start_lba_out, uint8_t *type_out)
{
    uint32_t i;
    bool found_any = false;
    bool found_fat = false;
    uint32_t first_start_lba = 0u;
    uint8_t first_type = 0u;
    uint32_t fat_start_lba = 0u;
    uint8_t fat_type = 0u;

    for (i = 0u; i < 4u; i++) {
        sd_partition_t part;

        sd_parse_partition_entry(mbr + 446u + (i * 16u), &part);
        sd_print_partition_entry(i, &part);

        if (part.type != 0u && part.start_lba != 0u && part.sector_count != 0u) {
            if (!found_any) {
                found_any = true;
                first_start_lba = part.start_lba;
                first_type = part.type;
            }
            if (!found_fat && sd_partition_type_is_fat_like(part.type)) {
                found_fat = true;
                fat_start_lba = part.start_lba;
                fat_type = part.type;
            }
        }
    }

    if (found_fat) {
        *start_lba_out = fat_start_lba;
        *type_out = fat_type;
        return true;
    }

    if (found_any) {
        *start_lba_out = first_start_lba;
        *type_out = first_type;
        return true;
    }

    return false;
}

static void sd_print_generic_bpb(const uint8_t *sector)
{
    uint16_t bytes_per_sector = read_le16(sector + 11u);
    uint8_t sectors_per_cluster = sector[13];
    uint16_t reserved = read_le16(sector + 14u);
    uint8_t fats = sector[16];
    uint16_t root_entries = read_le16(sector + 17u);
    uint32_t total_sectors = read_le16(sector + 19u);
    uint32_t fat_size = read_le16(sector + 22u);
    uint32_t hidden_sectors = read_le32(sector + 28u);

    if (total_sectors == 0u) {
        total_sectors = read_le32(sector + 32u);
    }
    if (fat_size == 0u) {
        fat_size = read_le32(sector + 36u);
    }

    usart1_puts("sd: BPB bytes_per_sector=");
    usart1_put_dec_u32(bytes_per_sector);
    usart1_puts(" sectors_per_cluster=");
    usart1_put_dec_u32(sectors_per_cluster);
    usart1_puts(" reserved=");
    usart1_put_dec_u32(reserved);
    usart1_puts(" fats=");
    usart1_put_dec_u32(fats);
    usart1_puts("\r\n");

    usart1_puts("sd: BPB root_entries=");
    usart1_put_dec_u32(root_entries);
    usart1_puts(" hidden_sectors=");
    usart1_put_dec_u32(hidden_sectors);
    usart1_puts(" total_sectors=");
    usart1_put_dec_u32(total_sectors);
    usart1_puts(" fat_sectors=");
    usart1_put_dec_u32(fat_size);
    usart1_puts("\r\n");
}

static void sd_print_boot_sector_summary(const uint8_t *sector, uint32_t lba)
{
    usart1_puts("sd: boot sector lba=");
    usart1_put_dec_u32(lba);
    usart1_puts(" signature=0x");
    usart1_put_hex8(sector[511]);
    usart1_put_hex8(sector[510]);
    usart1_puts("\r\n");

    if (sd_is_exfat_boot_sector(sector)) {
        uint64_t partition_offset = read_le64(sector + 64u);
        uint64_t volume_length = read_le64(sector + 72u);
        uint32_t fat_offset = read_le32(sector + 80u);
        uint32_t fat_length = read_le32(sector + 84u);
        uint32_t cluster_heap_offset = read_le32(sector + 88u);
        uint32_t cluster_count = read_le32(sector + 92u);
        uint32_t root_cluster = read_le32(sector + 96u);
        uint8_t sector_shift = sector[108];
        uint8_t cluster_shift = sector[109];
        uint32_t bytes_per_sector = 1u << sector_shift;
        uint32_t sectors_per_cluster = 1u << cluster_shift;

        usart1_puts("sd: filesystem=exFAT\r\n");
        usart1_puts("sd: exFAT bytes_per_sector=");
        usart1_put_dec_u32(bytes_per_sector);
        usart1_puts(" sectors_per_cluster=");
        usart1_put_dec_u32(sectors_per_cluster);
        usart1_puts(" fats=");
        usart1_put_dec_u32(sector[110]);
        usart1_puts(" root_cluster=");
        usart1_put_dec_u32(root_cluster);
        usart1_puts("\r\n");
        usart1_puts("sd: exFAT partition_offset=");
        usart1_put_dec_u64(partition_offset);
        usart1_puts(" volume_length=");
        usart1_put_dec_u64(volume_length);
        usart1_puts("\r\n");
        usart1_puts("sd: exFAT fat_offset=");
        usart1_put_dec_u32(fat_offset);
        usart1_puts(" fat_length=");
        usart1_put_dec_u32(fat_length);
        usart1_puts(" heap_offset=");
        usart1_put_dec_u32(cluster_heap_offset);
        usart1_puts(" cluster_count=");
        usart1_put_dec_u32(cluster_count);
        usart1_puts("\r\n");
        return;
    }

    if (sd_is_fat32_boot_sector(sector)) {
        usart1_puts("sd: filesystem=FAT32\r\n");
        sd_print_generic_bpb(sector);
        usart1_puts("sd: FAT32 root_cluster=");
        usart1_put_dec_u32(read_le32(sector + 44u));
        usart1_puts(" fsinfo=");
        usart1_put_dec_u32(read_le16(sector + 48u));
        usart1_puts(" backup_boot=");
        usart1_put_dec_u32(read_le16(sector + 50u));
        usart1_puts("\r\n");
        return;
    }

    if (sd_is_fat12_or_fat16_boot_sector(sector)) {
        usart1_puts("sd: filesystem=");
        if (sector_has_string(sector, 54u, "FAT12   ", 8u)) {
            usart1_puts("FAT12\r\n");
        } else {
            usart1_puts("FAT16\r\n");
        }
        sd_print_generic_bpb(sector);
        return;
    }

    usart1_puts("sd: filesystem type not recognized from boot sector\r\n");
}

static void sd_print_data_prefix(const char *label, const uint8_t *data, uint32_t count)
{
    uint32_t i;

    usart1_puts(label);
    for (i = 0u; i < count; i++) {
        if (i != 0u) {
            usart1_putc(' ');
        }
        usart1_put_hex8(data[i]);
    }
    usart1_puts("\r\n");
}

static bool sd_probe_fat32_aux(uint32_t volume_lba, const uint8_t *boot_sector)
{
    uint16_t fsinfo_sector = read_le16(boot_sector + 48u);
    uint16_t reserved = read_le16(boot_sector + 14u);
    uint32_t fat_lba = volume_lba + (uint32_t)reserved;

    if (fsinfo_sector != 0u && fsinfo_sector != 0xFFFFu) {
        uint32_t fsinfo_lba = volume_lba + (uint32_t)fsinfo_sector;
        uint32_t lead_sig;
        uint32_t struct_sig;
        uint32_t free_count;
        uint32_t next_free;
        uint32_t trail_sig;

        usart1_puts("sd: reading FSInfo sector at lba ");
        usart1_put_dec_u32(fsinfo_lba);
        usart1_puts("\r\n");

        if (!sd_read_block(fsinfo_lba, g_sector0)) {
            return false;
        }

        lead_sig = read_le32(g_sector0 + 0u);
        struct_sig = read_le32(g_sector0 + 484u);
        free_count = read_le32(g_sector0 + 488u);
        next_free = read_le32(g_sector0 + 492u);
        trail_sig = read_le32(g_sector0 + 508u);

        usart1_puts("sd: FSInfo lead=0x");
        usart1_put_hex32(lead_sig);
        usart1_puts(" struct=0x");
        usart1_put_hex32(struct_sig);
        usart1_puts(" trail=0x");
        usart1_put_hex32(trail_sig);
        usart1_puts("\r\n");
        usart1_puts("sd: FSInfo free_clusters=");
        if (free_count == 0xFFFFFFFFu) {
            usart1_puts("unknown");
        } else {
            usart1_put_dec_u32(free_count);
        }
        usart1_puts(" next_free=");
        if (next_free == 0xFFFFFFFFu) {
            usart1_puts("unknown");
        } else {
            usart1_put_dec_u32(next_free);
        }
        usart1_puts("\r\n");
    }

    usart1_puts("sd: reading FAT sector at lba ");
    usart1_put_dec_u32(fat_lba);
    usart1_puts("\r\n");
    if (!sd_read_block(fat_lba, g_sector0)) {
        return false;
    }
    sd_print_data_prefix("sd: FAT[0] first16=", g_sector0, 16u);
    return true;
}

static void sd_print_cid_summary(const uint8_t *cid)
{
    uint32_t serial = ((uint32_t)cid[9] << 24) |
                      ((uint32_t)cid[10] << 16) |
                      ((uint32_t)cid[11] << 8) |
                      (uint32_t)cid[12];
    uint32_t year = 2000u + sd_extract_bits(cid, 19u, 12u);
    uint32_t month = sd_extract_bits(cid, 11u, 8u);

    usart1_puts("sd: CID raw: ");
    sd_print_bytes(cid, 16u);

    usart1_puts("sd: CID MID=0x");
    usart1_put_hex8(cid[0]);
    usart1_puts(" OID=");
    usart1_putc((char)cid[1]);
    usart1_putc((char)cid[2]);
    usart1_puts(" PNM=");
    usart1_putc((char)cid[3]);
    usart1_putc((char)cid[4]);
    usart1_putc((char)cid[5]);
    usart1_putc((char)cid[6]);
    usart1_putc((char)cid[7]);
    usart1_puts(" PRV=");
    usart1_put_dec_u32((uint32_t)(cid[8] >> 4));
    usart1_putc('.');
    usart1_put_dec_u32((uint32_t)(cid[8] & 0x0Fu));
    usart1_puts(" PSN=0x");
    usart1_put_hex32(serial);
    usart1_puts(" MDT=");
    usart1_put_dec_u32(year);
    usart1_putc('-');
    if (month < 10u) {
        usart1_putc('0');
    }
    usart1_put_dec_u32(month);
    usart1_puts("\r\n");
}

static void sd_print_csd_summary(const uint8_t *csd)
{
    uint32_t csd_structure = sd_extract_bits(csd, 127u, 126u);
    uint32_t sector_count = 0u;
    uint32_t capacity_mib;

    usart1_puts("sd: CSD raw: ");
    sd_print_bytes(csd, 16u);
    usart1_puts("sd: CSD structure ");
    usart1_put_dec_u32(csd_structure);
    usart1_puts("\r\n");

    if (csd_structure == 1u) {
        uint32_t c_size = sd_extract_bits(csd, 69u, 48u);
        sector_count = (c_size + 1u) * 1024u;
    } else if (csd_structure == 0u) {
        uint32_t read_bl_len = sd_extract_bits(csd, 83u, 80u);
        uint32_t c_size = sd_extract_bits(csd, 73u, 62u);
        uint32_t c_size_mult = sd_extract_bits(csd, 49u, 47u);
        uint32_t block_len = 1u << read_bl_len;
        uint32_t blocknr = (c_size + 1u) * (1u << (c_size_mult + 2u));
        sector_count = (blocknr * block_len) / SD_SECTOR_SIZE;
    }

    if (sector_count != 0u) {
        capacity_mib = sector_count / 2048u;
        usart1_puts("sd: sectors=");
        usart1_put_dec_u32(sector_count);
        usart1_puts(" capacity_mib=");
        usart1_put_dec_u32(capacity_mib);
        usart1_puts("\r\n");
    } else {
        usart1_puts("sd: capacity parse unsupported for this CSD layout\r\n");
    }
}

static bool sd_card_init(uint32_t *ocr_out, uint8_t *cid, uint8_t *csd)
{
    uint32_t i;
    uint8_t r1;
    uint8_t r7[4];

    g_sd_is_sdhc = false;

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

    if (!sd_read_ocr(ocr_out)) {
        return false;
    }
    g_sd_is_sdhc = ((*ocr_out & 0x40000000u) != 0u);

    usart1_puts("sd: OCR=0x");
    usart1_put_hex32(*ocr_out);
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

    if (!sd_read_register(SD_CMD10, cid)) {
        return false;
    }
    if (!sd_read_register(SD_CMD9, csd)) {
        return false;
    }

    sd_spi_set_prescaler(SD_SPI_BR_RUN);
    return true;
}

int main(void)
{
    uint32_t ocr = 0u;
    uint32_t volume_lba = 0u;
    uint8_t volume_type = 0u;
    uint8_t cid[16];
    uint8_t csd[16];

    SystemCoreClockUpdate();
    SysTick_Config(SystemCoreClock / 1000u);
    led_init();
    usart1_init();
    sd_spi_init();

    usart1_puts("\r\nsd_spi_probe: STM32F103C8 SPI1 / USART1\r\n");
    usart1_puts("sd_spi_probe: PA4=CS PA5=SCK PA6=MISO PA7=MOSI\r\n");
    usart1_puts("sd_spi_probe: starting probe in 1000 ms\r\n");
    delay_ms(1000u);

    led_set(true);

    if (!sd_card_init(&ocr, cid, csd)) {
        led_set(false);
        usart1_puts("sd: init failed\r\n");
        while (1) {
            delay_ms(1000u);
        }
    }

    sd_print_cid_summary(cid);
    sd_print_csd_summary(csd);

    usart1_puts("sd: reading sector 0\r\n");
    if (!sd_read_block(0u, g_sector0)) {
        led_set(false);
        usart1_puts("sd: CMD17 block 0 failed\r\n");
        while (1) {
            delay_ms(1000u);
        }
    }

    sd_print_sector_prefix(g_sector0);
    usart1_puts("sd: sector0 signature=0x");
    usart1_put_hex8(g_sector0[511]);
    usart1_put_hex8(g_sector0[510]);
    usart1_puts("\r\n");

    if (sd_find_primary_volume(g_sector0, &volume_lba, &volume_type)) {
        usart1_puts("sd: selected partition type 0x");
        usart1_put_hex8(volume_type);
        usart1_puts("\r\n");
        usart1_puts("sd: reading boot sector at lba ");
        usart1_put_dec_u32(volume_lba);
        usart1_puts("\r\n");
        if (!sd_read_block(volume_lba, g_sector0)) {
            led_set(false);
            usart1_puts("sd: boot sector read failed\r\n");
            while (1) {
                delay_ms(1000u);
            }
        }
    } else {
        usart1_puts("sd: no partition entry found; treating sector 0 as boot sector\r\n");
        volume_lba = 0u;
    }

    sd_print_boot_sector_summary(g_sector0, volume_lba);
    if (sd_is_fat32_boot_sector(g_sector0)) {
        if (!sd_probe_fat32_aux(volume_lba, g_sector0)) {
            led_set(false);
            usart1_puts("sd: FAT32 auxiliary probe failed\r\n");
            while (1) {
                delay_ms(1000u);
            }
        }
    }
    usart1_puts("sd: probe complete\r\n");
    led_set(false);

    while (1) {
        delay_ms(1000u);
    }
}
