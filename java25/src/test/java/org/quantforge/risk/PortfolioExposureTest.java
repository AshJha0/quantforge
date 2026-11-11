package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.pricing.ShortRate;

/** xva-exposure-portfolio.md properties. */
class PortfolioExposureTest {
    private static final ShortRate.Curve CURVE = new ShortRate.Curve(
            new double[] {0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782},
            new double[] {0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332});
    private static final double[] PAY = {1, 2, 3, 4, 5};
    private static final double[] Q = {0.95, 0.99};

    /** A single swap at a reset date reproduces the wave 4a Jamshidian EE; payer minus receiver is the forward. */
    @Test
    void singleSwapIsTheSwaption() {
        ShortRate.Params p = new ShortRate.Params(ShortRate.Model.HULL_WHITE, 0.05, 0.01, 0.0, CURVE);
        List<PortfolioExposure.Swap> pay = List.of(new PortfolioExposure.Swap(1e7, 0.03, true, 0.0, PAY));
        List<PortfolioExposure.Swap> rec = List.of(new PortfolioExposure.Swap(1e7, 0.03, false, 0.0, PAY));
        for (int k = 1; k <= 4; k++) {
            double t = k;
            double[] rest = java.util.Arrays.copyOfRange(PAY, k, PAY.length);
            PortfolioExposure.Point a = PortfolioExposure.point(CURVE, 0.05, 0.01, pay, t, Q);
            double jam = ShortRate.swaption(p, t, rest, 0.03, true, 1e7).price();
            assertEquals(jam, a.ee(), 1e-6 + 1e-9 * jam);
            PortfolioExposure.Point b = PortfolioExposure.point(CURVE, 0.05, 0.01, rec, t, Q);
            assertEquals(a.ee(), -b.ene(), 1e-6 + 1e-9 * a.ee());
            double fwd = CURVE.df(t) - CURVE.df(5.0);
            for (double ti : rest) {
                fwd -= 0.03 * CURVE.df(ti);
            }
            assertEquals(1e7 * fwd, a.ee() + a.ene(), 1e-4);
            assertTrue(a.pfe()[1] >= a.pfe()[0] && a.pfe()[0] >= 0.0);
        }
    }

    /** Offsetting trades give zero exposure; PFE is never below 0 and rises with the quantile. */
    @Test
    void offsettingAndQuantileOrder() {
        List<PortfolioExposure.Swap> flat = List.of(new PortfolioExposure.Swap(1e7, 0.04, true, 0.0, PAY),
                new PortfolioExposure.Swap(1e7, 0.04, false, 0.0, PAY));
        PortfolioExposure.Point z = PortfolioExposure.point(CURVE, 0.05, 0.01, flat, 2.0, Q);
        assertEquals(0.0, z.ee(), 1e-6);
        assertEquals(0.0, z.pfe()[1], 1e-6);
        List<PortfolioExposure.Swap> mix = List.of(new PortfolioExposure.Swap(1e7, 0.035, true, 0.0, PAY),
                new PortfolioExposure.Swap(5e6, 0.04, false, 0.0, new double[] {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}));
        PortfolioExposure.Point m = PortfolioExposure.point(CURVE, 0.03, 0.015, mix, 3.0, new double[] {0.5, 0.95, 0.99});
        assertTrue(m.pfe()[2] >= m.pfe()[1] && m.pfe()[1] >= m.pfe()[0] && m.pfe()[0] >= 0.0);
        assertTrue(m.ee() >= 0.0 && m.ene() <= 0.0);
    }

    /** The returned PFE inverts the distribution: P(f <= PFE) = q, including on the narrow top of a long payer. */
    @Test
    void pfeInvertsTheDistribution() {
        double[] pay = new double[20];
        for (int i = 0; i < 20; i++) {
            pay[i] = i + 1.0;
        }
        List<PortfolioExposure.Swap> s20 = List.of(new PortfolioExposure.Swap(1e7, 0.039, true, 0.0, pay));
        for (double[] as : new double[][] {{0.03, 0.005}, {0.10, 0.015}}) {
            for (double t : new double[] {5.0, 17.0, 19.0}) {
                PortfolioExposure.Point pt = PortfolioExposure.point(CURVE, as[0], as[1], s20, t, Q);
                for (int j = 0; j < Q.length; j++) {
                    if (pt.pfe()[j] > 0.0) {
                        double pr = PortfolioExposure.probabilityAtMost(CURVE, as[0], as[1], s20, t, pt.pfe()[j]);
                        assertEquals(Q[j], pr, 1e-9, "t=" + t + " q=" + Q[j]);
                    }
                }
            }
        }
    }
}
