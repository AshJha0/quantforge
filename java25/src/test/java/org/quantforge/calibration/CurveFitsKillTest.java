package org.quantforge.calibration;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/**
 * Behaviour of the D38b robust fit and its basis condition check (curve-fits.md), plus rule E1 on both fits.
 * Reference reciprocal condition numbers come from numpy: 1 / (||A||_1 ||inv(A)||_1) with A the Gram matrix
 * scaled to unit diagonal. The three matrices put the largest inverse column sum in columns 2, 0 and 1.
 */
class CurveFitsKillTest {

    private static final double[][] X1 = {{1, 0.5, 0.2}, {1, -1, 3}, {2, 0.1, -0.7}, {0.3, 2, 1}};
    private static final double[][] X3 = {{1, 2, 0.1}, {0.2, 1, 3}, {4, -0.5, 1}, {1, 1, -2}, {0.7, -3, 0.4}};
    private static final double[][] X5 = {{1, 0.9, 0.1}, {1, 1.1, 0.3}, {1, 1.0, -0.2}, {1, 0.95, 0.05}};

    @Test
    void basisRcondMatchesTheOneNormDefinition() {
        assertEquals(0.46214792954581285, CurveFits.basisRcond(X1), 1e-13);
        assertEquals(0.6335035837720054, CurveFits.basisRcond(X3), 1e-13);
        assertEquals(0.0009936439365524229, CurveFits.basisRcond(X5), 1e-15);
    }

    @Test
    void basisRcondIsZeroForDependentColumns() {
        double[][] x = {{1, 2, 3}, {0, 1, 1}, {1, 0, 1}, {2, 1, 3}};
        assertTrue(CurveFits.basisRcond(x) < CurveFits.RCOND_MIN);
    }

    private static double[][] basis(double[] m, double tau) {
        double[][] x = new double[m.length][3];
        for (int j = 0; j < m.length; j++) {
            double u = m[j] / tau;
            double e = -Math.expm1(-u) / u;
            x[j] = new double[] {1.0, e, e - Math.exp(-u)};
        }
        return x;
    }

    /** First-order conditions of the Huber problem, checked from the returned betas alone. */
    private static void assertHuberOptimum(double[] m, double[] y, double tau, double delta, CurveFits.Robust fit) {
        double[][] x = basis(m, tau);
        double[] g = new double[3];
        double obj = 0.0;
        for (int j = 0; j < m.length; j++) {
            double r = fit.betas()[0] * x[j][0] + fit.betas()[1] * x[j][1] + fit.betas()[2] * x[j][2] - y[j];
            assertEquals(r, fit.residuals()[j], 1e-15);
            double psi = Math.max(-delta, Math.min(delta, r));
            for (int p = 0; p < 3; p++) {
                g[p] += psi * x[j][p];
            }
            double a = Math.abs(r);
            obj += a <= delta ? r * r / 2.0 : delta * a - delta * delta / 2.0;
        }
        for (double v : g) {
            assertTrue(Math.abs(v) < 1e-15, "first-order condition " + v);
        }
        assertEquals(obj, fit.objective(), 1e-18);
    }

    private static final double[] M = {0.5, 1, 2, 3, 5, 7, 10, 20, 30};
    private static final double TAU = 1.5;

    private static double[] curve(double[] noise) {
        double[] y = new double[M.length];
        double[][] x = basis(M, TAU);
        for (int j = 0; j < M.length; j++) {
            y[j] = 0.03 * x[j][0] - 0.01 * x[j][1] + 0.02 * x[j][2] + noise[j];
        }
        return y;
    }

    @Test
    void outliersOfBothSignsAreFlagged() {
        double[] y = curve(new double[] {2e-4, -1e-4, 0.01, 1e-4, -2e-4, 1.5e-4, -0.008, 0.0, 5e-5});
        double delta = 5e-4;
        CurveFits.Robust fit = CurveFits.robust(M, y, TAU, delta);
        assertHuberOptimum(M, y, TAU, delta, fit);
        assertArrayEquals(new int[] {2, 6}, fit.outliers());
        assertTrue(fit.residuals()[2] < -delta && fit.residuals()[6] > delta);
    }

    @Test
    void outlierSetShrinksAsDeltaGrows() {
        double[] y = curve(new double[] {2e-4, -1e-4, 0.01, 1e-4, -2e-4, 1.5e-4, -0.008, 0.0, 5e-5});
        CurveFits.Robust small = CurveFits.robust(M, y, TAU, 1e-4);
        assertHuberOptimum(M, y, TAU, 1e-4, small);
        assertTrue(small.outliers().length > 2);
        CurveFits.Robust large = CurveFits.robust(M, y, TAU, 1.0);
        assertHuberOptimum(M, y, TAU, 1.0, large);
        assertEquals(0, large.outliers().length);
    }

    @Test
    void manyOutliersStillSettle() {
        double[] y = curve(new double[] {0.004, -0.003, 0.002, -0.005, 0.001, -0.002, 0.006, -0.001, 0.003});
        double delta = 2e-4;
        CurveFits.Robust fit = CurveFits.robust(M, y, TAU, delta);
        assertHuberOptimum(M, y, TAU, delta, fit);
        for (int j : fit.outliers()) {
            assertTrue(Math.abs(fit.residuals()[j]) > delta);
        }
    }

    @Test
    void aPointLeavesTheWorkingSetBeforeTheFitSettles() {
        double[] y = curve(new double[] {0.0017, 0.0018, 0.0006, -0.0023, -0.0018, 0.0026, -0.0027, 0.0015, 0.0015});
        assertHuberOptimum(M, y, TAU, 1e-4, CurveFits.robust(M, y, TAU, 1e-4));
    }

    @Test
    void illConditionedBasisAboveTheThresholdIsFitted() {
        // numpy: rcond of the scaled Gram matrix is 5.24e-10, well above 1e-12.
        double[] m = {5.0, 5.1, 5.2, 5.3};
        double[] y = {0.030, 0.031, 0.0305, 0.0302};
        CurveFits.Robust fit = CurveFits.robust(m, y, 5.0, 1e-3);
        double[][] x = basis(m, 5.0);
        for (int j = 0; j < m.length; j++) {
            double r = fit.betas()[0] * x[j][0] + fit.betas()[1] * x[j][1] + fit.betas()[2] * x[j][2] - y[j];
            assertEquals(r, fit.residuals()[j], 1e-15);
        }
    }

    @Test
    void nearlyEqualMaturitiesAreSingular() {
        double[] m = {1.0, 1.0 + 1e-7, 1.0 + 2e-7, 1.0 + 3e-7};
        QfError e = assertThrows(QfError.class, () -> CurveFits.robust(m, new double[] {0.01, 0.02, 0.03, 0.04}, 1.0, 1e-3));
        assertEquals("E_SINGULAR", e.code());
    }

    @Test
    void singularBasisIsRejected() {
        double[] m = {1.0, 1.0, 1.0, 1.0};
        QfError e = assertThrows(QfError.class, () -> CurveFits.robust(m, new double[] {0.01, 0.02, 0.03, 0.04}, 1.0, 1e-3));
        assertEquals("E_SINGULAR", e.code());
    }

    private static void assertNonFinite(String field, Runnable call) {
        QfError e = assertThrows(QfError.class, call::run);
        assertEquals("E_DOMAIN", e.code());
        assertEquals(field, e.field());
    }

    @Test
    void robustRejectsNonFiniteInputs() {
        double[] m = {1, 2, 5, 10};
        double[] y = {0.01, 0.02, 0.025, 0.03};
        assertNonFinite("m", () -> CurveFits.robust(new double[] {1, Double.NaN, 5, 10}, y, 1.0, 1e-3));
        assertNonFinite("y", () -> CurveFits.robust(m, new double[] {0.01, Double.NaN, 0.025, 0.03}, 1.0, 1e-3));
        assertNonFinite("tau", () -> CurveFits.robust(m, y, Double.NaN, 1e-3));
        assertNonFinite("delta", () -> CurveFits.robust(m, y, 1.0, Double.POSITIVE_INFINITY));
    }

    @Test
    void smoothRejectsNonFiniteInputs() {
        double[] k = {1, 5, 10};
        double[] m = {1, 2, 5, 10};
        double[] y = {0.01, 0.02, 0.025, 0.03};
        double[] w = {1, 1, 1, 1};
        assertNonFinite("knots", () -> CurveFits.smooth(new double[] {1, Double.NaN, 10}, m, y, 0.1, w));
        assertNonFinite("m", () -> CurveFits.smooth(k, new double[] {1, 2, Double.NaN, 10}, y, 0.1, w));
        assertNonFinite("y", () -> CurveFits.smooth(k, m, new double[] {0.01, Double.NaN, 0.025, 0.03}, 0.1, w));
        assertNonFinite("lambda", () -> CurveFits.smooth(k, m, y, Double.NaN, w));
        assertNonFinite("w", () -> CurveFits.smooth(k, m, y, 0.1, new double[] {1, Double.NaN, 1, 1}));
    }
}
