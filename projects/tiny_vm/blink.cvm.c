/* tiny_vm minimal C-like source example */
const int ON = 1;
const int OFF = 0;
const int TICK_MS = 125;

while (1) {
    led_write(ON);
    delay_ms(TICK_MS);
    led_write(OFF);
    delay_ms(TICK_MS);
}
