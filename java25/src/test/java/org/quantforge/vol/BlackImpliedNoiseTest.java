package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

/** Far out-of-the-money implied vol where the price formula's rounding exceeds 1e-13 of the price (usecases_c). */
class BlackImpliedNoiseTest {
    @Test
    void farOtmCallConvergesInVol() {
        double f = 5050.250835420839;
        double x = 7070.0;
        double d = 0.9704455335485082;
        double price = 15.990935848660413;
        double v = Black.solve(false, 1.0, f, x, 1.0, d, price);
        assertEquals(0.18813979238808, v, 1e-12);
        assertEquals(price, Black.lognormal(1.0, f, x, 1.0, d, v), 1e-10);
    }
}
