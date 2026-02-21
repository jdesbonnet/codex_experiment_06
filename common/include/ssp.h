#ifndef SSP_H
#define SSP_H

#include <stdint.h>

void ssp0_init(void);
uint8_t ssp0_xfer(uint8_t v);
void ssp0_cs_low(void);
void ssp0_cs_high(void);

#endif
