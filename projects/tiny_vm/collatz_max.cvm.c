/* Collatz max-step search in tiny C subset.
 * Search range: 1..100
 * Output:
 *   best_n
 *   best_steps
 */

const int LIMIT = 100;

int n = 1;
int best_n = 1;
int best_steps = 0;

while (n < (LIMIT + 1)) {
    int x = n;
    int steps = 0;

    while (x > 1) {
        if ((x % 2) == 0) {
            /* x = x / 2 via repeated subtraction (subset has no divide yet). */
            int t = x;
            int half = 0;
            while (t > 1) {
                t = t - 2;
                half = half + 1;
            }
            x = half;
        } else {
            /* x = 3*x + 1 via additions (subset has no multiply yet). */
            int two_x = x + x;
            x = two_x + x;
            x = x + 1;
        }
        steps = steps + 1;
    }

    if (best_steps < steps) {
        best_steps = steps;
        best_n = n;
    }

    n = n + 1;
}

print_u32(best_n);
print_u32(best_steps);
