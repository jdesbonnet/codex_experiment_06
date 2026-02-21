#include "sram23lc1024.h"
#include "ssp.h"
#include "systick.h"

void sram_init(void)
{
    ssp0_init();
}

uint8_t sram_read_mode(void)
{
    uint8_t v;
    ssp0_cs_low();
    ssp0_xfer(0x05u);
    v = ssp0_xfer(0xFFu);
    ssp0_cs_high();
    return v;
}

void sram_write_mode(uint8_t v)
{
    ssp0_cs_low();
    ssp0_xfer(0x01u);
    ssp0_xfer(v);
    ssp0_cs_high();
}

int sram_test_simple(void)
{
    static uint8_t wbuf[256];
    static uint8_t rbuf[256];
    const uint8_t patterns[] = { 0xAAu, 0x55u };
    const uint32_t sram_size = 128u * 1024u;
    const uint32_t chunk = sizeof(wbuf);

    for (unsigned int p = 0; p < sizeof(patterns); p++) {
        uint8_t pat = patterns[p];

        ssp0_cs_low();
        ssp0_xfer(0x02u);
        ssp0_xfer(0x00u);
        ssp0_xfer(0x00u);
        ssp0_xfer(0x00u);
        for (uint32_t addr = 0; addr < sram_size; addr += chunk) {
            for (uint32_t i = 0; i < chunk; i++) {
                wbuf[i] = pat;
                ssp0_xfer(wbuf[i]);
            }
        }
        ssp0_cs_high();

        ssp0_cs_low();
        ssp0_xfer(0x03u);
        ssp0_xfer(0x00u);
        ssp0_xfer(0x00u);
        ssp0_xfer(0x00u);
        for (uint32_t addr = 0; addr < sram_size; addr += chunk) {
            for (uint32_t i = 0; i < chunk; i++) {
                rbuf[i] = ssp0_xfer(0xFFu);
            }
            for (uint32_t i = 0; i < chunk; i++) {
                if (rbuf[i] != pat) {
                    ssp0_cs_high();
                    return -1;
                }
            }
        }
        ssp0_cs_high();
    }

    return 0;
}

void sram_bandwidth_test(uint32_t *write_kb_s, uint32_t *write_ms,
                         uint32_t *read_kb_s, uint32_t *read_ms)
{
    const uint32_t sram_size = 128u * 1024u;
    const uint32_t chunk = 256u;
    uint32_t start_ms;
    uint32_t elapsed_ms;
    uint32_t bytes_per_s;

    /* Write bandwidth */
    start_ms = systick_millis();
    ssp0_cs_low();
    ssp0_xfer(0x02u);
    ssp0_xfer(0x00u);
    ssp0_xfer(0x00u);
    ssp0_xfer(0x00u);
    for (uint32_t addr = 0; addr < sram_size; addr += chunk) {
        for (uint32_t i = 0; i < chunk; i++) {
            ssp0_xfer(0x00u);
        }
    }
    ssp0_cs_high();
    elapsed_ms = systick_millis() - start_ms;
    if (elapsed_ms == 0u) {
        elapsed_ms = 1u;
    }
    bytes_per_s = (sram_size * 1000u) / elapsed_ms;
    *write_kb_s = bytes_per_s / 1024u;
    *write_ms = elapsed_ms;

    /* Read bandwidth */
    start_ms = systick_millis();
    ssp0_cs_low();
    ssp0_xfer(0x03u);
    ssp0_xfer(0x00u);
    ssp0_xfer(0x00u);
    ssp0_xfer(0x00u);
    for (uint32_t addr = 0; addr < sram_size; addr += chunk) {
        for (uint32_t i = 0; i < chunk; i++) {
            (void)ssp0_xfer(0xFFu);
        }
    }
    ssp0_cs_high();
    elapsed_ms = systick_millis() - start_ms;
    if (elapsed_ms == 0u) {
        elapsed_ms = 1u;
    }
    bytes_per_s = (sram_size * 1000u) / elapsed_ms;
    *read_kb_s = bytes_per_s / 1024u;
    *read_ms = elapsed_ms;
}
