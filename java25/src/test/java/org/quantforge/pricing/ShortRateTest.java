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

    /** G-28: a Bermudan is at least the scheme's own single-date value; a callable bond at most its no-call bond. */
    @Test
    void schemeBounds() {
        ShortRate.Params p = models()[2];
        ShortRateFd.Grid g = new ShortRateFd.Grid(101, 50, 6.0);
        double[] pay = {2.0, 3.0, 4.0, 5.0};
        double one = ShortRateFd.bermudan(p, pay, 0.04, true, 1.0, new double[] {1.0}, g);
        double berm = ShortRateFd.bermudan(p, pay, 0.04, true, 1.0, new double[] {1.0, 2.0, 3.0}, g);
        assertTrue(berm >= one);
        double euro = ShortRate.swaption(p, 1.0, pay, 0.04, true, 1.0).price();
        assertEquals(euro, one, 0.02 * euro);
        double[] bond = {1.0, 2.0, 3.0, 4.0, 5.0};
        double straight = ShortRateFd.callable(p, bond, 0.05, 1.0, new double[0], 1.0, g);
        double call = ShortRateFd.callable(p, bond, 0.05, 1.0, new double[] {2.0, 3.0}, 1.0, g);
        assertTrue(call <= straight);
        double cf = 0.0;
        for (int i = 0; i < bond.length; i++) {
            cf += 0.05 * CURVE.df(bond[i]);
        }
        cf += CURVE.df(5.0);
        assertEquals(cf, straight, 1e-3);
    }

    /** Wave 2e: cap minus floor equals the swaplet sum on the model's bonds. */
    @Test
    void capFloorParity() {
        double[] t = {0.5, 1.0, 1.5, 2.0};
        for (ShortRate.Params p : models()) {
            double r = 0.035;
            double cap = sum(ShortRateProducts.capFloor(p, r, t, 0.04, true, 1.0));
            double floor = sum(ShortRateProducts.capFloor(p, r, t, 0.04, false, 1.0));
            double sw = 0.0;
            for (int i = 1; i < t.length; i++) {
                sw += ShortRate.df0(p, r, t[i - 1]) - (1.0 + 0.04 * (t[i] - t[i - 1])) * ShortRate.df0(p, r, t[i]);
            }
            assertEquals(sw, cap - floor, 1e-12, p.model().name());
        }
    }

    /** Wave 2c: targets made at a known sigma give that sigma back. */
    @Test
    void calibrationRecoversSigma() {
        ShortRate.Params p = new ShortRate.Params(ShortRate.Model.HULL_WHITE, 0.05, 0.007, 0.0, CURVE);
        double[] pay = {2.0, 3.0, 4.0, 5.0};
        ShortRateProducts.Quote[] q = new ShortRateProducts.Quote[2];
        q[0] = new ShortRateProducts.Quote(1.0, pay, 0.04, true, ShortRate.swaption(p, 1.0, pay, 0.04, true, 1.0).price());
        double[] pay2 = {3.0, 4.0, 5.0};
        q[1] = new ShortRateProducts.Quote(2.0, pay2, 0.04, false,
                ShortRate.swaption(p, 2.0, pay2, 0.04, false, 1.0).price());
        assertEquals(0.007, ShortRateProducts.calibrate(CURVE, 0.05, q).sigma(), 1e-9);
    }

    private static double sum(double[] x) {
        double s = 0.0;
        for (double v : x) {
            s += v;
        }
        return s;
    }

    /**
     * aad-core.md: the AAD ladder equals this build's own Richardson bump of the scheme within G-9, and the
     * G-9 cost ratio (median of 21 timed runs after 5 warm-ups) is printed for the benchmark record.
     */
    @Test
    void aadLadderMatchesBumpAndReportsCost() {
        double[] times = {1, 2, 5, 10};
        double[] dfs = {0.97, 0.935, 0.81, 0.62};
        double[] pay = {2.0, 3.0, 4.0, 5.0, 6.0};
        double[] ex = {1.0, 2.0, 3.0, 4.0, 5.0};
        ShortRateFd.Grid g = new ShortRateFd.Grid(101, 50, 6.0);
        double a = 0.05;
        double sig = 0.01;
        BermudanLadder.Ladder l = BermudanLadder.ladder(times, dfs, a, sig, pay, 0.035, true, 1.0, ex, g);
        java.util.function.DoubleUnaryOperator bumpA = h -> price(times, dfs, a * (1 + h), sig, pay, ex, g);
        assertEquals(richardson(bumpA, a), l.dMeanReversion(), 1e-10 + 1e-6 * Math.abs(l.dMeanReversion()));
        java.util.function.DoubleUnaryOperator bumpS = h -> price(times, dfs, a, sig * (1 + h), pay, ex, g);
        assertEquals(richardson(bumpS, sig), l.dSigma(), 1e-10 + 1e-6 * Math.abs(l.dSigma()));
        for (int i = 0; i < dfs.length; i++) {
            int k = i;
            java.util.function.DoubleUnaryOperator bump = h -> {
                double[] d = dfs.clone();
                d[k] *= 1 + h;
                return price(times, d, a, sig, pay, ex, g);
            };
            double ref = richardson(bump, dfs[i]);
            assertEquals(ref, l.dDiscountFactors()[i], 1e-10 + 1e-6 * Math.abs(ref), "pillar " + i);
        }
        assertEquals(price(times, dfs, a, sig, pay, ex, g), l.price(), 1e-12);
        BermudanLadder.Ladder tape = BermudanLadder.ladderTape(times, dfs, a, sig, pay, 0.035, true, 1.0, ex, g);
        assertEquals(tape.price(), l.price(), 1e-15);
        assertEquals(tape.dMeanReversion(), l.dMeanReversion(), 1e-11 * Math.abs(tape.dMeanReversion()));
        assertEquals(tape.dSigma(), l.dSigma(), 1e-11 * Math.abs(tape.dSigma()));
        for (int i = 0; i < dfs.length; i++) {
            assertEquals(tape.dDiscountFactors()[i], l.dDiscountFactors()[i], 1e-14 + 1e-11 * Math.abs(tape.dDiscountFactors()[i]));
        }
    }

    private static double price(double[] times, double[] dfs, double a, double sig, double[] pay, double[] ex,
                                ShortRateFd.Grid g) {
        ShortRate.Params p = new ShortRate.Params(ShortRate.Model.HULL_WHITE, a, sig, 0.0,
                new ShortRate.Curve(times, dfs));
        return ShortRateFd.bermudan(p, pay, 0.035, true, 1.0, ex, g);
    }

    /** Q3a rule: relative bumps 1e-4 and 5e-5, Richardson-extrapolated central differences. */
    private static double richardson(java.util.function.DoubleUnaryOperator v, double x) {
        double h = 1e-4;
        double d1 = (v.applyAsDouble(h) - v.applyAsDouble(-h)) / (2 * h * x);
        double d2 = (v.applyAsDouble(h / 2) - v.applyAsDouble(-h / 2)) / (h * x);
        return (4 * d2 - d1) / 3;
    }

    /**
     * G-9 performance record on the inputs of {@code aadladder_g-0001}: median of 21 timed runs after 5 warm-ups
     * of one price and of price plus ladder, same thread. Printed, not asserted (timing is machine-dependent).
     */
    @Test
    void aadCostRatioG9() {
        double[] times = {0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
            10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782};
        double[] dfs = {0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332};
        double[] pay = {2.0, 3.0, 4.0, 5.0, 6.0};
        double[] ex = {1.0, 2.0, 3.0, 4.0, 5.0};
        ShortRateFd.Grid g = new ShortRateFd.Grid(101, 50, 6.0);
        ShortRate.Params p = new ShortRate.Params(ShortRate.Model.HULL_WHITE, 0.05, 0.01, 0.0,
                new ShortRate.Curve(times, dfs));
        double[] tp = new double[21];
        double[] tl = new double[21];
        double sink = 0.0;
        for (int r = -5; r < 21; r++) {
            long t0 = System.nanoTime();
            sink += ShortRateFd.bermudan(p, pay, 0.039462, true, 1e6, ex, g);
            long t1 = System.nanoTime();
            sink += BermudanLadder.ladder(times, dfs, 0.05, 0.01, pay, 0.039462, true, 1e6, ex, g).dSigma();
            long t2 = System.nanoTime();
            if (r >= 0) {
                tp[r] = t1 - t0;
                tl[r] = t2 - t1;
            }
        }
        java.util.Arrays.sort(tp);
        java.util.Arrays.sort(tl);
        assertTrue(Double.isFinite(sink));
        System.out.printf("G-9 aadladder_g-0001: price %.3f ms, price+ladder %.3f ms, ratio %.3f%n", tp[10] / 1e6,
                tl[10] / 1e6, tl[10] / tp[10]);
    }
}
