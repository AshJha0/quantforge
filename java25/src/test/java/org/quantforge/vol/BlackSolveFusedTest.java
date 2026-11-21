package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.SplittableRandom;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/**
 * The lognormal implied-vol path evaluates each term once (bench gate, stage K perf lane). Its result must be the
 * same double, or the same error code and message, as the KR-341 solver it replaced, which is kept here verbatim as
 * the reference (Black.java at 4c3b25fb, lognormal branch, built on the public price function).
 */
class BlackSolveFusedTest {
    private static double vega(double f, double x, double t, double d, double v) {
        double r = Math.sqrt(t);
        return d * f * r * Normal.pdf((Math.log(f / x) + v * v * t / 2.0) / (v * r));
    }

    private static double identified(double phi, double f, double x, double t, double d, double v, double price) {
        double root = v * Math.sqrt(t);
        double d1 = (Math.log(f / x) + v * v * t / 2.0) / root;
        double mag = d * (f * Normal.cdf(phi * d1) + x * Normal.cdf(phi * (d1 - root)));
        double scale = v * vega(f, x, t, d, v);
        double error = Math.abs(Black.lognormal(phi, f, x, t, d, v) - price) + 0x1p-52 * mag
                + 0x1p-1070 * (1.0 + d * (Math.abs(f) + Math.abs(x) + root));
        if (!(scale > 0.0) || error > 1e-10 * scale) {
            throw new QfError("E_NO_CONVERGENCE", "the price does not identify the vol in binary64");
        }
        return v;
    }

    /** The pre-change solver, lognormal branch, after the bracket search (identical in both). */
    private static double reference(double phi, double f, double x, double t, double d, double price) {
        double lo = 0.0;
        double hi = 1.0;
        while (Black.lognormal(phi, f, x, t, d, hi) < price) {
            lo = hi;
            hi *= 2.0;
            if (hi > 1e300) {
                throw new QfError("E_NO_CONVERGENCE", "no upper bracket for implied vol");
            }
        }
        double v = (lo + hi) / 2.0;
        for (int i = 0; i < 400; i++) {
            double val = Black.lognormal(phi, f, x, t, d, v);
            double diff = val - price;
            if (diff == 0.0) {
                return identified(phi, f, x, t, d, v, price);
            }
            if (diff > 0.0) {
                hi = v;
            } else {
                lo = v;
            }
            double vega = vega(f, x, t, d, v);
            double next = vega > 0.0 && val > 0.0 ? v - Math.log(val / price) * val / vega : Double.NaN;
            if (!(next > lo && next < hi)) {
                next = (lo + hi) / 2.0;
            }
            boolean done = Math.abs(next - v) <= 4e-16 * v;
            v = next;
            if (done) {
                break;
            }
        }
        boolean priced = Math.abs(Black.lognormal(phi, f, x, t, d, v) - price) <= 1e-13 * Math.max(1.0, price);
        boolean collapsed = hi - lo <= 1e-14 * hi
                && Math.abs(Black.lognormal(phi, f, x, t, d, v) - price) <= 1e-10 * Math.max(1.0, price);
        if (!priced && !collapsed) {
            throw new QfError("E_NO_CONVERGENCE", "implied vol did not converge: f=" + f + " x=" + x + " t=" + t + " d=" + d
                    + " price=" + price + " v=" + v + " value=" + Black.lognormal(phi, f, x, t, d, v));
        }
        return identified(phi, f, x, t, d, v, price);
    }

    private static String run(boolean fused, double phi, double f, double x, double t, double d, double price) {
        try {
            double v = fused ? Black.solve(false, phi, f, x, t, d, price) : reference(phi, f, x, t, d, price);
            return Long.toHexString(Double.doubleToRawLongBits(v));
        } catch (QfError e) {
            return e.code() + ": " + e.getMessage();
        }
    }

    @Test
    void sameDoubleOrSameErrorAsTheReference() {
        SplittableRandom rng = new SplittableRandom(20261121L);
        double[] phis = {1.0, -1.0, 0.5};
        int errors = 0;
        for (int i = 0; i < 4000; i++) {
            double phi = phis[i % phis.length];
            double f = Math.exp(rng.nextDouble(-3.0, 9.0));
            double x = f * Math.exp(rng.nextDouble(-4.0, 4.0));
            double t = Math.exp(rng.nextDouble(-6.0, 4.0));
            double d = rng.nextDouble(0.2, 1.0);
            double vol = Math.exp(rng.nextDouble(-6.0, 1.5));
            double price = i % 7 == 0 ? Black.lognormal(phi, f, x, t, d, vol) * (1.0 + 1e-9)
                    : Black.lognormal(phi, f, x, t, d, vol);
            double upper = phi > 0 ? d * f : d * x;
            if (!(price > d * Math.max(phi * (f - x), 0.0)) || !(price < upper)) {
                continue;
            }
            String want = run(false, phi, f, x, t, d, price);
            if (want.startsWith("E_")) {
                errors++;
            }
            assertEquals(want, run(true, phi, f, x, t, d, price), "case " + i);
        }
        // The grid reaches the refusal paths as well as the accepted ones.
        assertEquals(true, errors > 0, "no error case reached");
    }

    @Test
    void cdfGivenDensityMatchesCdf() {
        double[] xs = {0.0, -0.0, 1e-300, -1e-12, 0.3, -1.7, 1.999, 2.0, -2.0, 5.5, -9.25, 37.0, -39.9, 40.0, 40.5, -41.0,
            Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY};
        for (double x : xs) {
            assertEquals(Double.doubleToRawLongBits(Normal.cdf(x)), Double.doubleToRawLongBits(Normal.cdf(x, Normal.pdf(x))),
                    "x=" + x);
            assertEquals(Double.doubleToRawLongBits(Normal.cdf(-x)), Double.doubleToRawLongBits(Normal.cdf(-x, Normal.pdf(x))),
                    "-x=" + x);
        }
    }
}
