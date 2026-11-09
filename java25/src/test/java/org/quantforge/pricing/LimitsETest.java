package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.PdeEngine;
import org.quantforge.vol.Heston;
import org.quantforge.vol.Slv;
import org.quantforge.vol.Smile;
import org.quantforge.vol.Surfaces;

/**
 * Q5a: limit-case and convergence-order checks for the stage E numerical methods that have no
 * outside source (plan section 12.1). The same checks run in all four languages.
 */
class LimitsETest {
    private static final double X0 = Math.log(100.0);

    private static double[] order(double[] e) {
        double[] p = new double[e.length - 1];
        for (int i = 0; i < p.length; i++) {
            p[i] = Math.log(Math.abs(e[i] / e[i + 1])) / Math.log(2);
        }
        return p;
    }

    private static void band(double[] e, double lo, double hi) {
        for (double p : order(e)) {
            assertTrue(p >= lo && p <= hi, "observed order " + p);
        }
    }

    private static double fd(boolean american, double r, int nx, int nt) {
        return Exotics.fd(-1, american, 100, 100, 1, r, 0, 0.2, nx, nt, 5.0)[0];
    }

    /** Largest |L - 1| near ln(spot) when SLV reduces to Heston (flat 20%, v0 = theta, xi small). */
    private static double slvGap(int nx, int nv, int nt) {
        var flat = List.of(new Surfaces.Slice(1.0, new Smile.Svi(0.04, 0.0, 0.0, 0.0, 0.1)));
        var r = Slv.leverage(100.0, 1.0, 0.0, 0.0, new Heston.Params(0.04, 2.0, 0.04, 0.01, -0.7), flat,
                new Slv.Grid(nx, nv, nt, X0 - 1.0, X0 + 1.0, 0.25));
        assertEquals(1.0, r.mass(), 1e-3);
        double gap = 0;
        for (int i = 0; i < r.x().length; i++) {
            if (Math.abs(r.x()[i] - X0) < 0.3) {
                gap = Math.max(gap, Math.abs(r.leverage()[i] - 1));
            }
        }
        return gap;
    }

    @Test
    void slvHestonLimitLeverageOneWithinDiscretisationError() {
        double coarse = slvGap(41, 20, 20);
        double fine = slvGap(81, 40, 40);
        assertTrue(coarse < 0.07, "coarse " + coarse);
        assertTrue(fine < 0.6 * coarse, "fine " + fine); // about first order
    }

    @Test
    void fdAmericanPutMatchesFineTree() {
        double tree = Exotics.crr(-1, 100, 100, 1, 0.05, 0, 0.2, 1000)[0];
        // Backward Euler error at this grid is about 2e-3; the tree's about 5e-4.
        assertEquals(tree, fd(true, 0.05, 401, 1600), 5e-3);
    }

    @Test
    void fdAmericanPutZeroRateIsEuropean() {
        double am = fd(true, 0.0, 401, 400);
        assertEquals(fd(false, 0.0, 401, 400), am, 1e-12);
        assertEquals(Exotics.gbs(-1, 100, 100, 1, 0, 0, 0.2), am, 5e-3);
    }

    @Test
    void crankNicolsonSecondOrder() {
        double exact = Exotics.gbs(1, 100, 105, 1, 0.03, 0.02, 0.2);
        long[] js = {100, 200, 400};
        double[] e = new double[3];
        for (int i = 0; i < 3; i++) {
            e[i] = PdeEngine.solve(new PdeEngine.Inputs(true, 100, 105, 0.03, 0.01, 0.2, 1, js[i], js[i] / 2, 6.0, 2))
                    .price() - exact;
        }
        band(e, 1.8, 2.2);
    }

    @Test
    void fdReferenceSchemeOrders() {
        double exact = Exotics.gbs(-1, 100, 100, 1, 0.05, 0.05, 0.2);
        // Space: halve dx and quarter dt, so the O(dt) term keeps pace with O(dx^2).
        band(new double[] {fd(false, 0.05, 51, 25) - exact, fd(false, 0.05, 101, 100) - exact,
            fd(false, 0.05, 201, 400) - exact}, 1.8, 2.2);
        // Time: Richardson on successive differences at a fixed fine grid.
        double[] f = {fd(false, 0.05, 401, 50), fd(false, 0.05, 401, 100), fd(false, 0.05, 401, 200),
            fd(false, 0.05, 401, 400)};
        band(new double[] {f[0] - f[1], f[1] - f[2], f[2] - f[3]}, 0.8, 1.2);
    }

    @Test
    void crrFirstOrder() {
        double exact = Exotics.gbs(-1, 100, 100, 1, 0.05, 0.05, 0.2);
        int[] ns = {100, 200, 400};
        double[] e = new double[3];
        for (int i = 0; i < 3; i++) {
            e[i] = Exotics.crr(-1, 100, 100, 1, 0.05, 0, 0.2, ns[i])[1] - exact;
        }
        band(e, 0.8, 1.2);
    }
}
