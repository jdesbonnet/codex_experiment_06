#include "ch32fun.h"

extern void rust_blink_main(void);

int main(void)
{
	SystemInit();
	rust_blink_main();
	return 0;
}
