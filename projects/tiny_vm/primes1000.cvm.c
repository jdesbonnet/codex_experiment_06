int n = 2;
while (n < 1001) {
    int is_prime = 1;
    int d = 2;
    while (d < n) {
        if ((n % d) == 0) {
            is_prime = 0;
            d = n;
        } else {
            d = d + 1;
        }
    }
    if (is_prime == 1) {
        print_u32(n);
    }
    n = n + 1;
}
