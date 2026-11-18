package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** G2++ properties: parity, the curve at t = 0, the one-factor limit, small-a continuity. */
class G2ppTest {
    private static final ShortRate.Curve CURVE =
            new ShortRate.Curve(new double[] {1, 2, 5, 10}, new double[] {0.97, 0.935, 0.81, 0.62});

    private static G2pp.Params p(double a, double b, double eta, double rho) {
        return new G2pp.Params(CURVE, a, 0.01, b, eta, rho);
    }

    @Test
    void putCallParity() {
        G2pp.Params m = p(0.5, 0.05, 0.008, -0.75);
        double c = G2pp.bondOption(m, true, 0.86, 1.0, 5.0);
        double put = G2pp.bondOption(m, false, 0.86, 1.0, 5.0);
        assertEquals(CURVE.df(5.0) - 0.86 * CURVE.df(1.0), c - put, 1e-12);
    }

    @Test
    void curveAtTimeZeroWithZeroStates() {
        assertEquals(CURVE.df(7.0), G2pp.zcb(p(0.5, 0.05, 0.008, 0.3), 0, 0, 0.0, 7.0), 1e-14);
    }

    @Test
    void vanishingSecondFactorIsHullWhite() {
        double g = G2pp.bondOption(p(0.08, 0.05, 1e-12, 0.4), true, 0.9, 2.0, 6.0);
        ShortRate.Params hw = new ShortRate.Params(ShortRate.Model.HULL_WHITE, 0.08, 0.01, 0.0, CURVE);
        assertEquals(ShortRate.bondOption(hw, 0.0, true, 0.9, 2.0, 6.0), g, 1e-12);
    }

    @Test
    void smallMeanReversionIsContinuous() {
        double lo = G2pp.zcb(p(1e-4, 2e-4, 0.008, 0.3), 0.001, 0.001, 1.0, 8.0);
        double hi = G2pp.zcb(p(1.001e-4, 2.001e-4, 0.008, 0.3), 0.001, 0.001, 1.0, 8.0);
        assertEquals(lo, hi, 1e-6);
    }

    @Test
    void largeMeanReversionAtTauZeroAndTiny() {
        // t = 0: V(0) = 0 and V(T - 0) - V(T) = 0, so with zero states P(0, T) is the curve exactly.
        G2pp.Params big = new G2pp.Params(CURVE, 1e4, 0.01, 1e4, 0.01, 0.5);
        assertEquals(CURVE.df(2.0), G2pp.zcb(big, 0, 0, 0.0, 2.0), 1e-15);
        // t = 1e-200: V(t) is below 1e-600 (0 in double) and V(T - t) - V(T) is of order (sigma/a)^2 t, so
        // P = P(0, 2) / P(0, 1e-200) = P(0, 2) to rounding.
        assertEquals(CURVE.df(2.0), G2pp.zcb(big, 0, 0, 1e-200, 2.0), 1e-15);
    }

    @Test
    void domainChecks() {
        String[] fields = {"a", "sigma", "b", "eta", "rho"};
        double[][] bad = {{-1, 0.01, 0.05, 0.008, 0.3}, {0.5, 0, 0.05, 0.008, 0.3}, {0.5, 0.01, 0, 0.008, 0.3},
            {0.5, 0.01, 0.05, -0.008, 0.3}, {0.5, 0.01, 0.05, 0.008, 1.0}};
        for (int i = 0; i < bad.length; i++) {
            double[] q = bad[i];
            QfError e = assertThrows(QfError.class, () -> new G2pp.Params(CURVE, q[0], q[1], q[2], q[3], q[4]));
            assertEquals("E_DOMAIN", e.code());
            assertEquals(fields[i], e.field());
        }
        G2pp.Params m = p(0.5, 0.05, 0.008, 0.3);
        assertEquals("t_years", field(() -> G2pp.zcb(m, 0, 0, -0.1, 2.0)));
        assertEquals("maturity_years", field(() -> G2pp.zcb(m, 0, 0, 2.0, 2.0)));
        assertEquals("expiry_years", field(() -> G2pp.bondOption(m, true, 0.9, 0.0, 2.0)));
        assertEquals("expiry_years", field(() -> G2pp.bondOption(m, true, 0.9, 2.0, 2.0)));
        assertEquals("strike", field(() -> G2pp.bondOption(m, true, 0.0, 1.0, 2.0)));
    }

    private static String field(org.junit.jupiter.api.function.Executable run) {
        QfError e = assertThrows(QfError.class, run);
        assertEquals("E_DOMAIN", e.code());
        return e.field();
    }
}
