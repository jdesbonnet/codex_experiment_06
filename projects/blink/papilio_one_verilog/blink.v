module blink (
    input  wire clk,
    output wire blink_out
);
    // 32 MHz input clock from the Papilio One oscillator. Using bit 24 gives
    // a visible blink rate of roughly 0.95 Hz.
    reg [24:0] counter = 25'd0;

    always @(posedge clk) begin
        counter <= counter + 25'd1;
    end

    assign blink_out = counter[24];
endmodule
