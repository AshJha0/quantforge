package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Random;
import net.jqwik.api.Example;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.quantforge.core.QfError;
import org.quantforge.hedging.LeastSquaresHedge.Costs;
import org.quantforge.hedging.LeastSquaresHedge.Solution;

/**
 * Ruling I-48: the sign-state active-set method for the {@code |x|} terms of {@code hedge.qp.solve}. KKT checks of
 * the returned solution at 21, 50 and 200 instruments, and agreement with the {@code 2^k} orthant enumeration (the
 * test oracle) on random problems with up to 12 instruments carrying an {@code |x|} term.
 *
 * <p>KKT tolerance: every residual below {@code 1e-8} times the gradient scale {@code max(1, max_j |g_j|)}.
 */
class SignSearchTest {
    private static final double TOL = 1e-8;

    private static double[][] gaussian(Random rnd, int rows, int cols) {
        double[][] m = new double[rows][cols];
        for (double[] row : m) {
            for (int j = 0; j < cols; j++) {
                row[j] = rnd.nextGaussian();
            }
        }
        return m;
    }

    private static double[] uniform(Random rnd, int n, double from, double to) {
        double[] v = new double[n];
        for (int j = 0; j < n; j++) {
            v[j] = from + (to - from) * rnd.nextDouble();
        }
        return v;
    }

    /** Gradient of the smooth part: {@code 2 (A'W r + ridge x + cw impact x)}. */
    private static double[] smoothGradient(double[][] a, double[] w, double ridge, double cw, double[] impact,
            Solution s) {
        int n = s.x().length;
        double[] wr = new double[a.length];
        for (int i = 0; i < a.length; i++) {
            wr[i] = w[i] * s.residual()[i];
        }
        double[] g = Dense.mulT(a, wr, n);
        for (int j = 0; j < n; j++) {
            g[j] = 2.0 * (g[j] + ridge * s.x()[j] + (impact == null ? 0.0 : cw * impact[j] * s.x()[j]));
        }
        return g;
    }

    /**
     * Checks the KKT conditions without equalities: stationarity with the subgradient of {@code |x_j|} at zero
     * coordinates, bound feasibility and the multiplier signs at active bounds, margin feasibility and complementary
     * slackness, with the margin multiplier {@code mu} estimated from the free coordinates.
     */
    private static void assertKkt(double[][] a, double[] w, double ridge, double[] lo, double[] hi, Costs c,
            Solution s) {
        int n = s.x().length;
        double[] x = s.x();
        double[] g = smoothGradient(a, w, ridge, c.costWeight(), c.impact(), s);
        double scale = 1.0;
        for (double v : g) {
            scale = Math.max(scale, Math.abs(v));
        }
        double tol = TOL * scale;
        double[] h = c.halfSpreads() == null ? new double[n] : c.halfSpreads();
        double[] m = c.marginRates() == null ? new double[n] : c.marginRates();
        double mu = 0.0;
        if (c.marginRates() != null) {
            double margin = 0.0;
            for (int j = 0; j < n; j++) {
                margin += m[j] * Math.abs(x[j]);
            }
            assertTrue(margin <= c.marginLimit() * (1 + 1e-9) + 1e-12, "margin feasibility");
            double num = 0.0;
            double den = 0.0;
            for (int j = 0; j < n; j++) {
                boolean atBound = (lo != null && x[j] == lo[j]) || (hi != null && x[j] == hi[j]);
                if (x[j] != 0.0 && !atBound && m[j] > 0.0) {
                    double sj = Math.signum(x[j]);
                    num += -(g[j] + c.costWeight() * h[j] * sj) * m[j] * sj;
                    den += m[j] * m[j];
                }
            }
            mu = den > 0.0 ? num / den : 0.0;
            assertTrue(mu >= -tol, "margin multiplier sign");
            if (mu > tol) {
                assertEquals(c.marginLimit(), margin, 1e-8 * Math.max(1.0, c.marginLimit()), "complementary slackness");
            }
            mu = Math.max(mu, 0.0);
        }
        for (int j = 0; j < n; j++) {
            double kink = c.costWeight() * h[j] + mu * m[j];
            boolean atLo = lo != null && x[j] == lo[j];
            boolean atHi = hi != null && x[j] == hi[j];
            if (lo != null) {
                assertTrue(x[j] >= lo[j], "lower bound " + j);
            }
            if (hi != null) {
                assertTrue(x[j] <= hi[j], "upper bound " + j);
            }
            if (x[j] == 0.0 && !atLo && !atHi) {
                assertTrue(Math.abs(g[j]) <= kink + tol, "subgradient at zero, instrument " + j);
            } else if (x[j] != 0.0) {
                double stat = g[j] + kink * Math.signum(x[j]);
                if (atLo) {
                    assertTrue(stat >= -tol, "lower-bound multiplier sign " + j);
                } else if (atHi) {
                    assertTrue(stat <= tol, "upper-bound multiplier sign " + j);
                } else {
                    assertEquals(0.0, stat, tol, "stationarity " + j);
                }
            } else {
                // At 0 and on a bound: some subgradient t in [-1, 1] with the bound's multiplier of the right sign.
                double low = g[j] - kink;
                double high = g[j] + kink;
                assertTrue(atLo ? high >= -tol : low <= tol, "bound at zero " + j);
            }
        }
    }

    /** Runs one KKT case and returns how many instruments the costs leave at exactly 0. */
    private static int kktCase(int n, int m, long seed, boolean bounds, boolean margin) {
        Random rnd = new Random(seed);
        double[][] a = gaussian(rnd, m, n);
        double[] b = gaussian(rnd, 1, m)[0];
        for (int i = 0; i < m; i++) {
            b[i] *= 5.0;
        }
        double[] w = uniform(rnd, m, 0.5, 2.0);
        double ridge = m < n ? 0.1 : 0.0;
        double[] spreads = uniform(rnd, n, 0.0, 6.0); // large enough to leave some instruments at exactly 0
        double[] impact = uniform(rnd, n, 0.0, 0.05);
        double[] lo = bounds ? uniform(rnd, n, -2.0, 0.0) : null;
        double[] hi = bounds ? uniform(rnd, n, 0.0, 2.0) : null;
        double[] rates = null;
        Double limit = null;
        if (margin) {
            rates = uniform(rnd, n, 0.1, 1.0);
            Solution free = LeastSquaresHedge.solve(a, b, w, ridge, null, null, lo, hi, false,
                    new Costs(spreads, impact, 1.0, null, null));
            double mg = 0.0;
            for (int j = 0; j < n; j++) {
                mg += rates[j] * Math.abs(free.x()[j]);
            }
            limit = 0.5 * mg;
        }
        Costs c = new Costs(spreads, impact, 1.0, rates, limit);
        Solution s = LeastSquaresHedge.solve(a, b, w, ridge, null, null, lo, hi, false, c);
        assertKkt(a, w, ridge, lo, hi, c, s);
        int zeros = 0;
        for (double v : s.x()) {
            zeros += v == 0.0 ? 1 : 0;
        }
        return zeros;
    }

    @Example
    void kktHoldsAt21Instruments() {
        int zeros = kktCase(21, 30, 21L, false, false) + kktCase(21, 30, 2121L, true, false)
                + kktCase(21, 30, 212121L, false, true);
        assertTrue(zeros > 0, "the costs leave some instrument at exactly 0, so the kink test is exercised");
    }

    @Example
    void kktHoldsAt50Instruments() {
        int zeros = kktCase(50, 60, 50L, false, false) + kktCase(50, 60, 5050L, true, false)
                + kktCase(50, 60, 505050L, true, true);
        assertTrue(zeros > 0, "the costs leave some instrument at exactly 0, so the kink test is exercised");
    }

    @Example
    void kktHoldsAt200Instruments() {
        int zeros = kktCase(200, 80, 200L, false, false) + kktCase(200, 80, 200200L, false, true);
        assertTrue(zeros > 0, "the costs leave some instrument at exactly 0, so the kink test is exercised");
    }

    @Property(tries = 150)
    void signSearchAgreesWithTheEnumerationOracle(@ForAll long seed) {
        Random rnd = new Random(seed);
        int n = 1 + rnd.nextInt(12);
        int m = n + rnd.nextInt(4);
        double[][] a = gaussian(rnd, m, n);
        double[] b = gaussian(rnd, 1, m)[0];
        for (int i = 0; i < m; i++) {
            b[i] *= 3.0;
        }
        double[] w = uniform(rnd, m, 0.2, 2.0);
        double ridge = rnd.nextBoolean() ? 0.0 : 0.05;
        double[] spreads = uniform(rnd, n, 0.0, 1.0);
        double[] impact = rnd.nextBoolean() ? uniform(rnd, n, 0.0, 0.1) : null;
        double[] lo = null;
        double[] hi = null;
        if (rnd.nextBoolean()) {
            lo = uniform(rnd, n, -2.0, 0.5);
            hi = new double[n];
            for (int j = 0; j < n; j++) {
                hi[j] = lo[j] + 0.1 + 2.0 * rnd.nextDouble();
            }
        }
        double[][] eq = null;
        double[] e = null;
        if (n > 1 && rnd.nextInt(3) == 0) {
            eq = gaussian(rnd, 1, n);
            double[] x0 = new double[n];
            for (int j = 0; j < n; j++) {
                x0[j] = lo == null ? rnd.nextGaussian() : lo[j] + (hi[j] - lo[j]) * rnd.nextDouble();
            }
            e = new double[] {Dense.dot(eq[0], x0)};
        }
        double[] rates = null;
        Double limit = null;
        if (rnd.nextBoolean()) {
            rates = uniform(rnd, n, 0.0, 1.0);
            limit = 0.2 + 3.0 * rnd.nextDouble();
        }
        Costs c = new Costs(spreads, impact, rnd.nextDouble() * 2.0, rates, limit);
        Solution oracle;
        try {
            oracle = LeastSquaresHedge.solveByEnumeration(a, b, w, ridge, eq, e, lo, hi, c);
        } catch (QfError err) {
            final double[][] eqf = eq;
            final double[] ef = e;
            final double[] lof = lo;
            final double[] hif = hi;
            QfError mine = org.junit.jupiter.api.Assertions.assertThrows(QfError.class,
                    () -> LeastSquaresHedge.solve(a, b, w, ridge, eqf, ef, lof, hif, false, c));
            assertEquals(err.code(), mine.code());
            return;
        }
        Solution s = LeastSquaresHedge.solve(a, b, w, ridge, eq, e, lo, hi, false, c);
        double fScale = Math.max(1.0, Math.abs(oracle.objective()));
        assertEquals(oracle.objective(), s.objective(), 1e-9 * fScale, "objective");
        for (int j = 0; j < n; j++) {
            assertEquals(oracle.x()[j], s.x()[j], 1e-7 * Math.max(1.0, Math.abs(oracle.x()[j])), "x " + j);
        }
    }
}
