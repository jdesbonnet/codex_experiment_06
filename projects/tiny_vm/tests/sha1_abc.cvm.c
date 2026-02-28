/* SHA-1 single-block regression over the ASCII string "abc".
 * Reference: FIPS PUB 180-4, Secure Hash Standard (SHS), SHA-1.
 * Expected output:
 *   A9993E36
 *   4706816A
 *   BA3E2571
 *   7850C26C
 *   9CD0D89D
 */

const int K0 = 0x5A827999;
const int K1 = 0x6ED9EBA1;
const int K2 = 0x8F1BBCDC;
const int K3 = 0xCA62C1D6;

const int H0_INIT = 0x67452301;
const int H1_INIT = 0xEFCDAB89;
const int H2_INIT = 0x98BADCFE;
const int H3_INIT = 0x10325476;
const int H4_INIT = 0xC3D2E1F0;

int i = 0;
int h0 = 0;
int h1 = 0;
int h2 = 0;
int h3 = 0;
int h4 = 0;
int a = 0;
int b = 0;
int c = 0;
int d = 0;
int e = 0;
int w = 0;
int f = 0;
int k = 0;
int s = 0;
int temp = 0;

while (i < 64) {
    store32le(i, 0);
    i = i + 4;
}

store32le(0, 0x61626380);
store32le(60, 24);

h0 = H0_INIT;
h1 = H1_INIT;
h2 = H2_INIT;
h3 = H3_INIT;
h4 = H4_INIT;

a = h0;
b = h1;
c = h2;
d = h3;
e = h4;

i = 0;
while (i < 80) {
    if (i < 16) {
        s = load32le(i * 4);
    } else {
        s = xor32(load32le(((i - 3) % 16) * 4), load32le(((i - 8) % 16) * 4));
        s = xor32(s, load32le(((i - 14) % 16) * 4));
        s = xor32(s, load32le(((i - 16) % 16) * 4));
        s = rol32(s, 1);
        store32le((i % 16) * 4, s);
    }

    w = s;

    if (i < 20) {
        f = or32(and32(b, c), and32(not32(b), d));
        k = K0;
    } else {
        if (i < 40) {
            f = xor32(xor32(b, c), d);
            k = K1;
        } else {
            if (i < 60) {
                f = or32(or32(and32(b, c), and32(b, d)), and32(c, d));
                k = K2;
            } else {
                f = xor32(xor32(b, c), d);
                k = K3;
            }
        }
    }

    temp = rol32(a, 5) + f;
    temp = temp + e;
    temp = temp + w;
    temp = temp + k;

    e = d;
    d = c;
    c = rol32(b, 30);
    b = a;
    a = temp;

    i = i + 1;
}

h0 = h0 + a;
h1 = h1 + b;
h2 = h2 + c;
h3 = h3 + d;
h4 = h4 + e;

print_hex32(h0);
print_hex32(h1);
print_hex32(h2);
print_hex32(h3);
print_hex32(h4);
