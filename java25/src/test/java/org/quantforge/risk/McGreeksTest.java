package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/** G-10 acceptance: smoothed pathwise variance below bump, likelihood-ratio delta within 3 SE of the closed form. */
class McGreeksTest {
    @Test
    void digitalCallAcceptance() {
        long n = 100_000;
        double s = 100;
        double r = 0.03;
        double v = 0.2;
        double d2 = (Math.log(1.0) + (r - v * v / 2) * 1.0) / v;
        double exact = Math.exp(-r) * Math.exp(-d2 * d2 / 2) / Math.sqrt(2 * Math.PI) / (s * v);
        McGreeks.Result pw = McGreeks.run(McGreeks.Payoff.DIGITAL_CALL, McGreeks.Method.PATHWISE, s, 100, 1, r, 0, v,
                n, 20261109L, 1.0, 0.0);
        McGreeks.Result bump = McGreeks.run(McGreeks.Payoff.DIGITAL_CALL, McGreeks.Method.BUMP, s, 100, 1, r, 0, v,
                n, 20261109L, 0.0, 0.01);
        McGreeks.Result lr = McGreeks.run(McGreeks.Payoff.DIGITAL_CALL, McGreeks.Method.LIKELIHOOD_RATIO, s, 100, 1, r,
                0, v, n, 20261109L, 0.0, 0.0);
        assertTrue(pw.deltaSe() < bump.deltaSe(), "smoothed pathwise variance below bump");
        assertEquals(exact, lr.delta(), 3 * lr.deltaSe());
    }
}
