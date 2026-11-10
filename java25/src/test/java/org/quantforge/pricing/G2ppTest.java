package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

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
}
