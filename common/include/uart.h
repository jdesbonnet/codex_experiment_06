#ifndef UART_H
#define UART_H

void uart_init_57600(void);
void uart_putc(char c);
void uart_puts(const char *s);
void uart_put_hex8(unsigned char v);
void uart_put_dec_u32(unsigned int v);

#endif
