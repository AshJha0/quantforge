package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Random;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.quantforge.core.QfError;
import org.quantforge.hedging.LeastSquaresHedge.Costs;
import org.quantforge.hedging.LeastSquaresHedge.Solution;

/** Wave 4a: hedge costs, impact and margin; the spec's property tests and every new validation path. */
class HedgeCostsTest {
    private static final double[][] A = {{1.0, 0.5, 0.2}, {0.3, 1.2, 0.4}, {0.1, 0.6, 1.5}, {0.8, 0.2, 0.9}};
    private static final double[] B = {-2.0, 1.5, -0.7, 0.9};
    private static final double[] W = {1.0, 2.0, 0.5, 1.5};

    private static Solution qp(double[][] eq, double[] e, double[] lo, double[] hi, boolean minNorm, Costs c) {
        return LeastSquaresHedge.solve(A, B, W, 0.0, eq, e, lo, hi, minNorm, c);
    }

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    private static double[][] gaussian(Random rnd, int rows, int cols) {
        double[][] m = new double[rows][cols];
        for (double[] row : m) {
            for (int j = 0; j < cols; j++) {
                row[j] = rnd.nextGaussian();
            }
        }
        return m;
    }

    private static double[] uniform(Random rnd, int n, double scale) {
        double[] v = new double[n];
        for (int j = 0; j < n; j++) {
            v[j] = scale * rnd.nextDouble();
        }
        return v;
    }

    @Property(tries = 100)
    void zeroCostWeightGivesTheWaveOneAnswer(@ForAll long seed) {
        Random rnd = new Random(seed);
        int n = 1 + rnd.nextInt(4);
        int m = n + rnd.nextInt(3);
        double[][] a = gaussian(rnd, m, n);
        double[] b = gaussian(rnd, 1, m)[0];
        double[] w = uniform(rnd, m, 1.0);
        for (int i = 0; i < m; i++) {
            w[i] += 0.1;
        }
        Solution plain = LeastSquaresHedge.solve(a, b, w, 0.0, null, null, null, null, false);
        Solution zero = LeastSquaresHedge.solve(a, b, w, 0.0, null, null, null, null, false,
                new Costs(uniform(rnd, n, 1.0), uniform(rnd, n, 1.0), 0.0, null, null));
        for (int j = 0; j < n; j++) {
            assertEquals(plain.x()[j], zero.x()[j], 1e-10 * Math.max(1.0, Math.abs(plain.x()[j])));
        }
        assertEquals(plain.objective(), zero.risk(), 1e-10 * Math.max(1.0, plain.objective()));
    }

    @Property(tries = 60)
    void frontierRiskRisesAndCostFalls(@ForAll long seed) {
        Random rnd = new Random(seed);
        int n = 1 + rnd.nextInt(4);
        int m = n + rnd.nextInt(3);
        double[][] a = gaussian(rnd, m, n);
        double[] b = gaussian(rnd, 1, m)[0];
        double[] w = new double[m];
        java.util.Arrays.fill(w, 1.0);
        double[] spreads = uniform(rnd, n, 0.5);
        double[] impact = uniform(rnd, n, 0.2);
        double prevRisk = -1.0;
        double prevCost = Double.POSITIVE_INFINITY;
        for (double cw : new double[] {0.0, 0.1, 0.5, 1.0, 3.0, 10.0}) {
            Solution s = LeastSquaresHedge.solve(a, b, w, 0.0, null, null, null, null, false,
                    new Costs(spreads, impact, cw, null, null));
            assertTrue(s.risk() >= prevRisk - 1e-9 * Math.max(1.0, prevRisk), "risk falls at " + cw);
            assertTrue(s.cost() <= prevCost + 1e-9 * Math.max(1.0, s.cost()), "cost rises at " + cw);
            prevRisk = s.risk();
            prevCost = s.cost();
        }
    }

    @Property(tries = 100)
    void anActiveMarginLimitIsMetExactly(@ForAll long seed) {
        Random rnd = new Random(seed);
        int n = 2 + rnd.nextInt(3);
        double[][] a = gaussian(rnd, n + 1, n);
        double[] b = gaussian(rnd, 1, n + 1)[0];
        double[] w = new double[n + 1];
        java.util.Arrays.fill(w, 1.0);
        double[] rates = uniform(rnd, n, 1.0);
        for (int j = 0; j < n; j++) {
            rates[j] += 0.05;
        }
        Solution free = LeastSquaresHedge.solve(a, b, w, 0.0, null, null, null, null, false);
        double freeMargin = 0.0;
        for (int j = 0; j < n; j++) {
            freeMargin += rates[j] * Math.abs(free.x()[j]);
        }
        double limit = 0.5 * freeMargin;
        Solution s = LeastSquaresHedge.solve(a, b, w, 0.0, null, null, null, null, false,
                new Costs(null, null, 1.0, rates, limit));
        assertEquals(limit, s.margin(), 1e-9 * Math.max(1.0, limit));
        assertTrue(s.risk() >= free.objective() - 1e-12);
    }

    @net.jqwik.api.Example
    void aCostlyInstrumentIsLeftOutExactly() {
        Solution s = qp(null, null, null, null, false, new Costs(new double[] {0, 0, 50}, null, 1.0, null, null));
        assertEquals(0.0, s.x()[2], 0.0);
        assertEquals(Double.doubleToLongBits(0.0), Double.doubleToLongBits(s.x()[2]));
        assertNull(s.margin());
        assertEquals(s.risk() + s.cost(), s.objective(), 1e-14);
        Solution plain = qp(null, null, null, null, false, null);
        assertNull(plain.risk());
    }

    @net.jqwik.api.Example
    void impactRegularisesASingularProblemButASpreadDoesNot() {
        double[][] dup = {{1, 1}, {2, 2}};
        double[] b = {1, 2};
        double[] w = {1, 1};
        Solution s = LeastSquaresHedge.solve(dup, b, w, 0, null, null, null, null, false,
                new Costs(null, new double[] {0.1, 0.1}, 1.0, null, null));
        assertEquals(s.x()[0], s.x()[1], 1e-12);
        assertEquals("E_SINGULAR", code(() -> LeastSquaresHedge.solve(dup, b, w, 0, null, null, null, null, false,
                new Costs(new double[] {0.1, 0.1}, null, 1.0, null, null))));
    }

    @net.jqwik.api.Example
    void marginWithEqualitiesAndInfeasibleLimits() {
        double[][] eq = {{1, 1, 1}};
        Solution s = qp(eq, new double[] {1}, null, null, false, new Costs(null, null, 1.0,
                new double[] {1, 1, 1}, 5.0));
        assertEquals(1.0, s.x()[0] + s.x()[1] + s.x()[2], 1e-12);
        assertEquals("E_INFEASIBLE", code(() -> qp(eq, new double[] {1}, null, null, false,
                new Costs(null, null, 1.0, new double[] {1, 1, 1}, 0.5))));
        double[][] fix = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};
        Solution fixed = qp(fix, new double[] {1, -1, 0}, null, null, false, new Costs(null, null, 1.0,
                new double[] {1, 1, 1}, 2.0));
        assertArrayEquals(new double[] {1, -1, 0}, fixed.x(), 1e-14);
        assertEquals(2.0, fixed.margin(), 1e-14);
        assertEquals("E_INFEASIBLE", code(() -> qp(fix, new double[] {1, -1, 0}, null, null, false,
                new Costs(null, null, 1.0, new double[] {1, 1, 1}, 1.0))));
    }

    @net.jqwik.api.Example
    void costChecksRunInTheSpecifiedOrder() {
        double[] three = {0.1, 0.1, 0.1};
        assertEquals("E_INPUT", code(() -> qp(null, null, null, null, false, new Costs(new double[] {1}, null, 1,
                null, null))));
        assertEquals("E_INPUT", code(() -> qp(null, null, null, null, false, new Costs(null, new double[] {1}, 1,
                null, null))));
        assertEquals("E_INPUT", code(() -> qp(null, null, null, null, false, new Costs(null, null, 1,
                new double[] {1}, 1.0))));
        assertEquals("E_INPUT", code(() -> qp(null, null, null, null, false, new Costs(null, null, 1, three,
                null))));
        assertEquals("E_INPUT", code(() -> qp(null, null, null, null, false, new Costs(null, null, 1, null, 1.0))));
        assertEquals("E_INPUT", code(() -> qp(null, null, null, null, true, new Costs(three, null, 1, null, null))));
        assertEquals("E_DOMAIN", code(() -> qp(null, null, null, null, false, new Costs(new double[] {-1, 0, 0},
                null, 1, null, null))));
        assertEquals("E_DOMAIN", code(() -> qp(null, null, null, null, false, new Costs(null,
                new double[] {0, -1, 0}, 1, null, null))));
        assertEquals("E_DOMAIN", code(() -> qp(null, null, null, null, false, new Costs(null, null, 1,
                new double[] {0, 0, -1}, 1.0))));
        assertEquals("E_DOMAIN", code(() -> qp(null, null, null, null, false, new Costs(three, null, -1, null,
                null))));
        assertEquals("E_DOMAIN", code(() -> qp(null, null, null, null, false, new Costs(null, null, 1, three,
                -1.0))));
        double[] many = new double[21];
        java.util.Arrays.fill(many, 0.1);
        // Ruling I-48: no size limit below the I-4 one (the 20-instrument orthant cap is gone).
        assertEquals(21, LeastSquaresHedge.solve(new double[][] {many}, new double[] {1}, new double[] {1}, 1.0, null,
                null, null, null, false, new Costs(many, null, 1, null, null)).x().length);
    }
}
