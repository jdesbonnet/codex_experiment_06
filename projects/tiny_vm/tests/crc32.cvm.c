/* CRC-32 test over the byte sequence "123456789".
 * Polynomial: 0xEDB88320 (reflected)
 * Expected output:
 *   CBF43926
 */

const int POLY = 0xEDB88320;
const int ALL_BITS = 0xFFFFFFFF;

store8(0, 49);
store8(1, 50);
store8(2, 51);
store8(3, 52);
store8(4, 53);
store8(5, 54);
store8(6, 55);
store8(7, 56);
store8(8, 57);

int i = 0;
int crc = ALL_BITS;

while (i < 9) {
    crc = xor32(crc, load8(i));
    int bit = 0;
    while (bit < 8) {
        if (and32(crc, 1) == 1) {
            crc = shr32(crc, 1);
            crc = xor32(crc, POLY);
        } else {
            crc = shr32(crc, 1);
        }
        bit = bit + 1;
    }
    i = i + 1;
}

crc = xor32(crc, ALL_BITS);
print_hex32(crc);
