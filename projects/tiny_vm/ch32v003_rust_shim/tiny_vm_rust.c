#include "ch32fun.h"

extern void rust_tiny_vm_main(void);

int main(void)
{
	SystemInit();
	rust_tiny_vm_main();
	return 0;
}
