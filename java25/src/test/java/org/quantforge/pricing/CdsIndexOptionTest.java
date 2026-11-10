package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.constraints.DoubleRange;
import net.jqwik.api.constraints.Scale;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** R7: parity on the adjusted pair (property), limit cases and every input check at its edge. */
class CdsIndexOptionTest {
    private static final LocalDate AS_OF = LocalDate.of(2026, 11, 9);
    private static final LocalDate EXPIRY = LocalDate.of(2027, 3, 20);
    private static final LocalDate MATURITY = LocalDate.of(2031, 12, 20);

    private static CreditOptions.IndexOption price(boolean payer, double h, double rec, double k, double c,
                                                   double n, double vol) {
        return CreditOptions.indexOption(AS_OF, EXPIRY, MATURITY, 0.03, h, rec, payer, k, c, n, vol);
    }

    @Property(tries = 200)
    void parityOnTheAdjustedPair(@ForAll @Scale(6) @DoubleRange(min = 0.002, max = 0.08) double h,
                                 @ForAll @Scale(6) @DoubleRange(min = 0.0, max = 0.7) double rec,
                                 @ForAll @Scale(6) @DoubleRange(min = 0.002, max = 0.05) double k,
                                 @ForAll @Scale(6) @DoubleRange(min = 0.0, max = 0.05) double c,
                                 @ForAll @Scale(6) @DoubleRange(min = 0.0, max = 1.5) double vol) {
        CreditOptions.IndexOption p;
        CreditOptions.IndexOption r;
        try {
            p = price(true, h, rec, k, c, 1e7, vol);
            r = price(false, h, rec, k, c, 1e7, vol);
        } catch (QfError e) {
            assertEquals("E_DOMAIN", e.code()); // K_adj <= 0 for a strike far below a large coupon
            return;
        }
        double want = 1e7 * p.annuity() * (p.adjustedForward() - p.adjustedStrike());
        assertEquals(want, p.price() - r.price(), 1e-10 * Math.max(Math.abs(want), p.price() + r.price()));
    }

    @Test
    void limits() {
        CreditOptions.IndexOption atCoupon = price(true, 0.02, 0.4, 0.01, 0.01, 1.0, 0.5);
        assertEquals(0.01, atCoupon.adjustedStrike(), 1e-15);
        assertEquals(0.0, atCoupon.exerciseUpfront(), 0.0);
        CreditOptions.IndexOption zeroVol = price(true, 0.02, 0.4, 0.008, 0.01, 1.0, 0.0);
        assertEquals(zeroVol.annuity() * Math.max(zeroVol.adjustedForward() - zeroVol.adjustedStrike(), 0.0),
                zeroVol.price(), 1e-15);
        // the strike hazard reprices the strike from expiry
        double hk = zeroVol.strikeHazard();
        assertEquals(0.008, CreditOptions.legs(EXPIRY, EXPIRY, MATURITY, 0.03, hk, 0.4).forward(), 1e-14);
    }

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    @Test
    void checksAtTheirEdges() {
        assertEquals("E_INPUT", code(() -> CreditOptions.indexOption(AS_OF, AS_OF, MATURITY, 0.03, 0.02, 0.4, true,
                0.01, 0.01, 1.0, 0.3)));
        assertEquals("E_INPUT", code(() -> CreditOptions.indexOption(AS_OF, EXPIRY, EXPIRY, 0.03, 0.02, 0.4, true,
                0.01, 0.01, 1.0, 0.3)));
        assertEquals("E_DOMAIN", code(() -> price(true, 0.02, 1.0, 0.01, 0.01, 1.0, 0.3)));
        assertEquals("E_DOMAIN", code(() -> price(true, 0.02, -1e-300, 0.01, 0.01, 1.0, 0.3)));
        assertEquals("E_DOMAIN", code(() -> price(true, -1e-300, 0.4, 0.01, 0.01, 1.0, 0.3)));
        assertEquals("E_DOMAIN", code(() -> price(true, 0.02, 0.4, 0.0, 0.01, 1.0, 0.3)));
        assertEquals("E_DOMAIN", code(() -> price(true, 0.02, 0.4, 0.01, -1e-300, 1.0, 0.3)));
        assertEquals("E_DOMAIN", code(() -> price(true, 0.02, 0.4, 0.01, 0.01, 1.0, -1e-300)));
        assertEquals("E_DOMAIN", code(() -> price(true, 0.02, 0.4, 0.01, 0.01, 0.0, 0.3)));
        assertEquals("E_DOMAIN", code(() -> price(true, 0.0, 0.4, 0.01, 0.01, 1.0, 0.3))); // F_adj = 0
        assertEquals("E_DOMAIN", code(() -> price(true, 0.02, 0.4, Double.NaN, 0.01, 1.0, 0.3)));
        // boundary values that pass
        price(true, 0.02, 0.0, 0.01, 0.0, 1.0, 0.0);
    }
}
