/* Rotate test over a fixed 32-bit word.
 * Expected output:
 *   34567812
 *   78123456
 */

const int X = 0x12345678;

print_hex32(rol32(X, 8));
print_hex32(ror32(X, 8));
