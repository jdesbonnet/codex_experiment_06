/* Simple bounded buffer/checksum test.
 * Writes 5 bytes into tiny_vm scratch memory, then sums them.
 * Expected output:
 *   15
 */

store8(0, 1);
store8(1, 2);
store8(2, 3);
store8(3, 4);
store8(4, 5);

int i = 0;
int sum = 0;

while (i < 5) {
    sum = sum + load8(i);
    i = i + 1;
}

print_u32(sum);
