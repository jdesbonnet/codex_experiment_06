#ifndef SRAM23LC1024_H
#define SRAM23LC1024_H

#include <stdint.h>

void sram_init(void);
uint8_t sram_read_mode(void);
void sram_write_mode(uint8_t v);
int sram_test_simple(void);
void sram_bandwidth_test(uint32_t *write_kb_s, uint32_t *write_ms,
                         uint32_t *read_kb_s, uint32_t *read_ms);

#endif
