package org.quantforge.calibration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Valid input where the old robust fit failed: at the minimum one residual sits within 1e-7 of delta
 * (mutation re-check 2026-11-18). Not a golden, because the spec keeps golden residuals 1e-6 from
 * delta. The same input is in the Python, C++ and Rust tests.
 */
class CurveFitsRobustTest {

    @Test
    void convergesWithAResidualNearDelta() {
        double[] m = {3.8740307873000113, 7.757472624115791, 24.769272470090453, 24.76936904673551};
        double[] y = {0.022406223051166397, 0.0025821078676810487, 0.052253746187190836, 0.04025167916426023};
        double tau = 2.1121330519140273;
        double delta = 0.0010283264459667806;
        CurveFits.Robust fit = CurveFits.robust(m, y, tau, delta);
        double[] g = new double[3];
        double nearest = Double.MAX_VALUE;
        for (int j = 0; j < m.length; j++) {
            double u = m[j] / tau;
            double e = -Math.expm1(-u) / u;
            double[] x = {1.0, e, e - Math.exp(-u)};
            double r = fit.residuals()[j];
            double psi = Math.max(-delta, Math.min(delta, r));
            for (int p = 0; p < 3; p++) {
                g[p] += psi * x[p];
            }
            nearest = Math.min(nearest, Math.abs(Math.abs(r) - delta));
        }
        for (double v : g) {
            assertTrue(Math.abs(v) < 1e-14, "first-order condition");
        }
        assertTrue(nearest < 1e-7);
        assertEquals(1, fit.outliers().length);
        assertEquals(2, fit.outliers()[0]);
    }
}
