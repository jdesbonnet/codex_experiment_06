/* 32-bit scratch-memory access test.
 * Expected output:
 *   12345678
 *   A5A5A5A5
 */

store32le(0, 0x12345678);
store32le(4, 0xA5A5A5A5);

print_hex32(load32le(0));
print_hex32(load32le(4));
