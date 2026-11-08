package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** E2 by independent routes: limits, parity, series against integral, operator conservation. */
class HestonTest {
    private static final Heston.Params P = new Heston.Params(0.04, 1.5, 0.05, 0.6, -0.7);
    private static final double[] K = {70, 90, 100, 110, 140};

    @Test
    void cfIsOneAtMinusIAndParityHolds() {
        Heston.C z = Heston.cf(new Heston.C(0.0, -1.0), 2.0, P);
        assertEquals(1.0, z.re(), 1e-13);
        assertEquals(0.0, z.im(), 1e-13);
        double[] c = Heston.prices(100, 1.0, 0.03, 0.01, true, K, P, null);
        double[] p = Heston.prices(100, 1.0, 0.03, 0.01, false, K, P, null);
        for (int i = 0; i < K.length; i++) {
            assertEquals(100 * Math.exp(-0.01) - K[i] * Math.exp(-0.03), c[i] - p[i], 1e-10);
        }
    }

    @Test
    void smallVolOfVolTendsToBlackScholesAtTheAverageVariance() {
        Heston.Params h = new Heston.Params(0.09, 2.0, 0.04, 1e-4, -0.5);
        double t = 1.0;
        double vbar = 0.04 + (0.09 - 0.04) * (1 - Math.exp(-2.0 * t)) / (2.0 * t);
        double[] c = Heston.prices(100, t, 0.03, 0.0, true, K, h, null);
        double f = 100 * Math.exp(0.03);
        for (int i = 0; i < K.length; i++) {
            // the gap is first order in xi (about 1e-4 here): a 5e-4 bound separates vbar from v0 or theta,
            // which miss by more than 0.5
            assertEquals(Black.lognormal(1.0, f, K[i], t, Math.exp(-0.03), Math.sqrt(vbar)), c[i], 5e-4);
        }
    }

    @Test
    void batesWithoutJumpsIsHestonAndMertonSeriesMatchesTheIntegral() {
        Heston.Jumps none = new Heston.Jumps(0.0, -0.1, 0.2);
        double[] h = Heston.prices(100, 1.0, 0.03, 0.01, true, K, P, null);
        double[] b = Heston.prices(100, 1.0, 0.03, 0.01, true, K, P, none);
        for (int i = 0; i < K.length; i++) {
            assertEquals(h[i], b[i], 1e-14);
        }
        Heston.Jumps j = new Heston.Jumps(0.8, -0.12, 0.15);
        double v = 0.2;
        double t = 0.75;
        double[] series = Heston.merton(100, t, 0.03, 0.01, true, K, v, j);
        double f = 100 * Math.exp(0.02 * t);
        for (int i = 0; i < K.length; i++) {
            double lewis = Heston.lewis(f, K[i], 0.03, t, true, u -> {
                Heston.C bs = u.times(u).plus(new Heston.C(0.0, 1.0).times(u)).times(-v * v * t / 2.0).exp();
                return bs.times(Heston.jumpFactor(u, t, j));
            });
            assertEquals(lewis, series[i], 1e-9);
        }
        double[] bs = Heston.merton(100, t, 0.03, 0.01, false, K, v, none);
        assertEquals(Black.lognormal(-1.0, f, 100, t, Math.exp(-0.03 * t), v), bs[2], 1e-13);
    }

    @Test
    void domainChecks() {
        assertThrows(QfError.class, () -> new Heston.Params(0.04, 1.5, 0.05, 0.0, -0.7).check());
        assertThrows(QfError.class, () -> new Heston.Params(0.04, 1.5, 0.05, 0.6, 1.0).check());
        assertThrows(QfError.class, () -> new Heston.Jumps(-1.0, 0.0, 0.1).check());
        assertThrows(QfError.class, () -> new Slv.Grid(4, 50, 50, 3.4, 5.8, 0.25).check(100));
        assertEquals("E_LIMIT", assertThrows(QfError.class,
                () -> new Slv.Grid(1001, 50, 50, 3.4, 5.8, 0.25).check(100)).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> new Slv.Grid(61, 50, 50, 3.4, 5.8, 0.0).check(100)).code());
    }

    @Test
    void noFluxOperatorConservesMassAndThomasSolves() {
        double[] mu = {0.3, 0.1, -0.2, -0.4, 0.05, 0.2};
        double[] s = {0.01, 0.02, 0.03, 0.02, 0.04, 0.05};
        double[][] m = Slv.rows(mu, s, 0.1, 0.01, true);
        for (int col = 0; col < mu.length; col++) {
            double sum = m[col][1];
            if (col > 0) {
                sum += m[col - 1][2];
            }
            if (col < mu.length - 1) {
                sum += m[col + 1][0];
            }
            assertEquals(1.0, sum, 1e-15);
        }
        double[] x = {1, -2, 3, 0.5, 4, -1};
        double[] d = new double[x.length];
        for (int k = 0; k < x.length; k++) {
            d[k] = m[k][1] * x[k] + (k > 0 ? m[k][0] * x[k - 1] : 0) + (k < x.length - 1 ? m[k][2] * x[k + 1] : 0);
        }
        double[] y = Slv.thomas(m, d);
        for (int k = 0; k < x.length; k++) {
            assertEquals(x[k], y[k], 1e-13);
        }
    }

    @Test
    void flatSurfaceZeroCorrelationLeverageIsNearOneAtTheMoney() {
        // flat 20% smile (b = 0) and Heston with theta = v0 = 0.04: leverage near 1 near the money
        Smile.Svi flat = new Smile.Svi(0.04, 0.0, 0.0, 0.0, 0.1);
        List<Surfaces.Slice> sl = List.of(new Surfaces.Slice(0.5, new Smile.Svi(0.02, 0.0, 0.0, 0.0, 0.1)), new Surfaces.Slice(1.0, flat));
        // with rho = 0, high-variance paths spread further in x, so near the money E[v | x] is below the mean
        // and L is above 1 by an amount that grows with xi; with a small xi, L is close to 1
        double x0 = Math.log(100);
        Slv.Grid grid = new Slv.Grid(61, 50, 50, x0 - 1.2, x0 + 1.2, 0.25);
        Slv.Result wide = Slv.leverage(100, 1.0, 0.0, 0.0, new Heston.Params(0.04, 2.0, 0.04, 0.3, 0.0), sl, grid);
        Slv.Result calm = Slv.leverage(100, 1.0, 0.0, 0.0, new Heston.Params(0.04, 2.0, 0.04, 0.05, 0.0), sl, grid);
        assertTrue(wide.leverage()[30] > 1.0 && wide.leverage()[30] < 1.06);
        assertTrue(Math.abs(calm.leverage()[30] - 1.0) < Math.abs(wide.leverage()[30] - 1.0));
        assertEquals(1.0, calm.leverage()[30], 0.01);
        assertTrue(wide.mass() > 0.95 && wide.mass() < 1.01);
    }
}
