package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.quantforge.core.Rng;

/** Stage G acceptance properties: parity, curve reproduction, short-rate limit, swaption parity, BGK against MC. */
class ShortRateTest {
    private static final ShortRate.Curve CURVE =
            new ShortRate.Curve(new double[] {1, 2, 5, 10}, new double[] {0.97, 0.935, 0.81, 0.62});

    private static ShortRate.Params[] models() {
        return new ShortRate.Params[] {
            new ShortRate.Params(ShortRate.Model.VASICEK, 0.15, 0.012, 0.045, null),
            new ShortRate.Params(ShortRate.Model.CIR, 0.3, 0.05, 0.04, null),
            new ShortRate.Params(ShortRate.Model.HULL_WHITE, 0.08, 0.01, 0.0, CURVE)};
    }

    @Test
    void putCallParity() {
        for (ShortRate.Params p : models()) {
            double r = 0.035;
            double k = 0.86;
            double c = ShortRate.bondOption(p, r, true, k, 1.0, 5.0);
            double put = ShortRate.bondOption(p, r, false, k, 1.0, 5.0);
            double pt = p.model() == ShortRate.Model.HULL_WHITE ? CURVE.df(1.0) : ShortRate.zcb(p, r, 0.0, 1.0);
            double ps = p.model() == ShortRate.Model.HULL_WHITE ? CURVE.df(5.0) : ShortRate.zcb(p, r, 0.0, 5.0);
            assertEquals(ps - k * pt, c - put, 1e-12, p.model().name());
        }
    }

    @Test
    void hullWhiteAtTimeZeroIsTheCurve() {
        ShortRate.Params p = models()[2];
        for (double t : new double[] {0.5, 1.0, 3.0, 12.0}) {
            assertEquals(CURVE.df(t), ShortRate.zcb(p, CURVE.forward(0.0), 0.0, t), 1e-14 * CURVE.df(t));
        }
    }

    @Test
    void zeroRateTendsToTheShortRate() {
        double r = 0.031;
        for (ShortRate.Params p : models()) {
            double t = p.model() == ShortRate.Model.HULL_WHITE ? 0.0 : 1.0;
            double tau = 1e-6;
            double df = ShortRate.zcb(p, p.model() == ShortRate.Model.HULL_WHITE ? CURVE.forward(0.0) : r, t, t + tau);
            double expected = p.model() == ShortRate.Model.HULL_WHITE ? CURVE.forward(0.0) : r;
            assertEquals(expected, -Math.log(df) / tau, 1e-6, p.model().name());
        }
    }

    @Test
    void smallMeanReversionIsContinuous() {
        ShortRate.Params lo = new ShortRate.Params(ShortRate.Model.VASICEK, 1e-4, 0.012, 0.045, null);
        ShortRate.Params lo2 = new ShortRate.Params(ShortRate.Model.VASICEK, 1.0001e-4, 0.012, 0.045, null);
        assertEquals(ShortRate.zcb(lo, 0.03, 0, 5), ShortRate.zcb(lo2, 0.03, 0, 5), 1e-6);
    }

    @Test
    void swaptionPayerMinusReceiverIsTheForwardSwap() {
        ShortRate.Params p = models()[2];
        double[] pay = {2, 3, 4, 5};
        ShortRate.Swaption payer = ShortRate.swaption(p, 1.0, pay, 0.03, true, 1.0);
        ShortRate.Swaption rec = ShortRate.swaption(p, 1.0, pay, 0.03, false, 1.0);
        assertEquals(payer.annuity() * (payer.forwardSwapRate() - 0.03), payer.price() - rec.price(), 1e-8);
    }

    /** R9 acceptance: daily down-and-out call and put against an exact-date Monte Carlo, 3 standard errors. */
    @Test
    void dailyBarrierMatchesExactDateMonteCarlo() {
        int paths = 40_000;
        int steps = 252;
        double s0 = 100;
        double k = 100;
        double h = 90;
        double r = 0.05;
        double q = 0.02;
        double v = 0.25;
        Rng rng = Rng.seeded(20261109L, 0);
        double dt = 1.0 / steps;
        double drift = (r - q - v * v / 2) * dt;
        double vol = v * Math.sqrt(dt);
        double[] call = new double[paths];
        double[] put = new double[paths];
        for (int i = 0; i < paths; i++) {
            double s = s0;
            boolean alive = true;
            for (int j = 0; j < steps; j++) {
                s *= Math.exp(drift + vol * rng.nextNormal());
                alive &= s > h;
            }
            double df = Math.exp(-r);
            call[i] = alive ? df * Math.max(s - k, 0) : 0;
            put[i] = alive ? df * Math.max(k - s, 0) : 0;
        }
        for (int c = 0; c < 2; c++) {
            double[] x = c == 0 ? call : put;
            double mean = 0;
            for (double y : x) {
                mean += y;
            }
            mean /= paths;
            double var = 0;
            for (double y : x) {
                var += (y - mean) * (y - mean);
            }
            double se = Math.sqrt(var / (paths - 1) / paths);
            double bgk = Exotics.barrierDiscrete(c == 0 ? 1 : -1,
                    Exotics.BarrierType.DOWN_OUT, s0, k, 1.0, r, q, v, h, 0.0, steps);
            assertTrue(Math.abs(bgk - mean) < 3 * se, "case " + c + " bgk " + bgk + " mc " + mean + " se " + se);
        }
    }

    /** xva-exposure.md: PAY minus RECEIVE EE at each reset equals the forward value of the remaining swap. */
    @Test
    void exposurePayMinusReceiveIsForwardSwap() {
        ShortRate.Params p = models()[2];
        double[] pay = {1.0, 2.0, 3.0, 4.0, 5.0};
        double k = 0.045;
        double n = 1e7;
        for (int j = 0; j < pay.length - 1; j++) {
            double t = j == 0 ? 0.5 : pay[j - 1];
            double[] rest = java.util.Arrays.copyOfRange(pay, j, pay.length);
            double fwd = CURVE.df(t) - CURVE.df(rest[rest.length - 1]);
            double prev = t;
            for (double ti : rest) {
                fwd -= k * (ti - prev) * CURVE.df(ti);
                prev = ti;
            }
            double diff = ShortRate.swaption(p, t, rest, k, true, n).price()
                    - ShortRate.swaption(p, t, rest, k, false, n).price();
            assertEquals(n * fwd, diff, 1e-6);
        }
    }
}
