#ifndef SYSTICK_H
#define SYSTICK_H

#include <stdint.h>

void systick_init_1ms(void);
uint32_t systick_millis(void);

#endif
