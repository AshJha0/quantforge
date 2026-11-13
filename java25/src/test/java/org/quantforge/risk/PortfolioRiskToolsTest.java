package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** Property tests of xva-framework.md, portfolio-risk-tools.md, f3-sensitivities.md and frtb-sa-fx-equity.md. */
class PortfolioRiskToolsTest {
    private static final double[] T = {0.0, 0.25, 0.5, 0.75, 1.0};
    private static final double[][] V = {{0, 3, 5, 2, -1}, {0, -2, -4, -6, -3}, {0, 1, 6, 9, 4}, {0, 0.5, -1, 2.5, 7}};

    @Test
    void zeroThresholdsNoLagGiveZeroExposure() {
        Xva.Profile p = Xva.profile(T, V, new Xva.Csa(0, 0, 0, 0, 0), 0.75);
        for (double e : p.ee()) {
            assertEquals(0.0, e, 0.0);
        }
        assertEquals(0.0, p.epe(), 0.0);
    }

    @Test
    void collateralNeverRaisesExposureWithoutLag() {
        Xva.Profile none = Xva.profile(T, V, null, 0.75);
        Xva.Profile csa = Xva.profile(T, V, new Xva.Csa(1, 1, 0, 0, 0), 0.75);
        for (int i = 0; i < T.length; i++) {
            assertEquals(true, csa.ee()[i] <= none.ee()[i] + 1e-15);
        }
    }

    @Test
    void wwrWithZeroBIsTheIndependentCva() {
        double[] t = {0.25, 0.5, 0.75, 1.0};
        double[][] v = new double[V.length][4];
        for (int p = 0; p < V.length; p++) {
            System.arraycopy(V[p], 1, v[p], 0, 4);
        }
        double[] df = {0.995, 0.99, 0.985, 0.98};
        double[] a = new double[4];
        double wwr = Xva.wwrCva(t, v, df, 0.03, 0.4, 0.0, a);
        double[] ee = new double[4];
        for (int i = 0; i < 4; i++) {
            for (double[] row : v) {
                ee[i] += Math.max(row[i], 0.0) / v.length;
            }
        }
        double[] adj = Xva.adjustments(t, df, ee, new double[4], 0.03, 0.4, 0.0, 0.4, 0, 0, false, null, 0, null, 0);
        assertEquals(adj[0], wwr, 1e-14);
        assertEquals(Math.log(0.03), a[2], 1e-13);
        double ww = Xva.wwrCva(t, v, df, 0.03, 0.4, 0.3, a);
        assertEquals(true, ww > wwr);
    }

    @Test
    void zeroOwnHazardGivesZeroDva() {
        double[] t = {0.5, 1.0};
        double[] r = Xva.adjustments(t, new double[] {0.99, 0.98}, new double[] {10, 20}, new double[] {-5, -6}, 0.02,
                0.4, 0.0, 0.4, 0.01, 0.01, true, null, 0, null, 0);
        assertEquals(0.0, r[1], 0.0);
        assertEquals(r[2] - r[3], r[4], 1e-15);
    }

    @Test
    void simmSingleFactorAndConcentration() {
        double[] ws = new double[1];
        double[] r = Xva.simm(new double[] {10_000}, new double[] {90}, new double[][] {{1}}, 1e9, ws);
        assertEquals(900_000.0, r[1], 1e-9);
        r = Xva.simm(new double[] {4e6}, new double[] {1}, new double[][] {{1}}, 1e6, ws);
        assertEquals(2.0, r[0], 1e-15);
    }

    @Test
    void reverseStressAndHorizonLimits() {
        double k = PortfolioRiskTools.reverseScale(new double[] {1}, new double[] {-1275}, new double[][] {{0}}, 50);
        assertEquals(50.0 / 1275.0, k, 1e-15);
        assertEquals(1.0, PortfolioRiskTools.varianceRatio(0.0, 10), 0.0);
        assertEquals(1.4375, PortfolioRiskTools.varianceRatio(0.2, 10), 1e-4);
    }

    @Test
    void sensitivitiesAgreeWithBumps() {
        double h = 1e-6;
        double[] up = PortfolioRiskTools.bsmYield(true, 100, 100, 1, 0.03, 0.025 + h, 0.25);
        double[] dn = PortfolioRiskTools.bsmYield(true, 100, 100, 1, 0.03, 0.025 - h, 0.25);
        double[] mid = PortfolioRiskTools.bsmYield(true, 100, 100, 1, 0.03, 0.025, 0.25);
        assertEquals((up[0] - dn[0]) / (2 * h), mid[1], 1e-6);
        double[] c = PortfolioRiskTools.bsmYield(true, 100, 90, 1, 0.03, 0.02, 0.25);
        double[] p = PortfolioRiskTools.bsmYield(false, 100, 90, 1, 0.03, 0.02, 0.25);
        assertEquals(100 * Math.exp(-0.02) - 90 * Math.exp(-0.03), c[0] - p[0], 1e-12);
        double[] m0 = PortfolioRiskTools.margrabe(100, 95, 0.3, 0.25, 0.5 - 1e-6, 1);
        double[] m1 = PortfolioRiskTools.margrabe(100, 95, 0.3, 0.25, 0.5 + 1e-6, 1);
        double[] m = PortfolioRiskTools.margrabe(100, 95, 0.3, 0.25, 0.5, 1);
        assertEquals((m1[0] - m0[0]) / 2e-6 * 0.01, m[1], 1e-8);
        assertEquals(PortfolioRiskTools.inflation01(1e7, 10, 0.027, 0.75),
                (PortfolioRiskTools.zcisPv(1e7, 10, 0.025, 0.027 + 1e-6, 0.75)
                        - PortfolioRiskTools.zcisPv(1e7, 10, 0.025, 0.027 - 1e-6, 0.75)) / 2e-6 * 1e-4, 1e-4);
    }

    @Test
    void frtbOneFactorIsWeightTimesSensitivity() {
        assertEquals(150_000.0, FrtbSbm.fx(List.of("EURUSD"), new double[] {1e6}, Set.of()).capital(), 1e-9);
        assertEquals(300_000.0, FrtbSbm.equity(List.of("A"), new long[] {5}, List.of("SPOT"), new double[] {1e6})
                .capital(), 1e-9);
        assertEquals(50_000.0, FrtbSbm.csr(List.of("A"), new long[] {3}, List.of("5Y"), List.of("BOND"),
                new double[] {1e6}).capital(), 1e-9);
        assertEquals(350_000.0, FrtbSbm.commodity(List.of("B"), new long[] {2}, List.of("1Y"), List.of("ICE"),
                new double[] {1e6}).capital(), 1e-9);
        // bucket 11 equity: simple sum, no offset between names
        FrtbGirr.Result r = FrtbSbm.equity(List.of("X", "Y"), new long[] {11, 11}, List.of("SPOT", "SPOT"),
                new double[] {1e6, -1e6});
        assertEquals(1_400_000.0, r.capital(), 1e-6);
    }

    /** frtb-sa-vega-curvature.md: one vega factor gives RW x VR; long gamma alone gives no curvature charge. */
    @Test
    void vegaAndCurvatureLimits() {
        FrtbVegaCurvature.RiskClass fx = FrtbVegaCurvature.RiskClass.FX;
        assertEquals(1e6, FrtbVegaCurvature.vega(fx, List.of(new FrtbVegaCurvature.Vega("EURUSD", "", 1, 0, 1e6)))
                .capital(), 1e-9);
        FrtbVegaCurvature.RiskClass eq = FrtbVegaCurvature.RiskClass.EQUITY;
        assertEquals(0.7778e6, FrtbVegaCurvature.vega(eq, List.of(new FrtbVegaCurvature.Vega("5", "A", 1, 0, 1e6)))
                .capital(), 1e-9);
        assertEquals(0.0, FrtbVegaCurvature.curvature(eq, List.of(new FrtbVegaCurvature.Cvr("5", "A", -3, 0)), false)
                .capital(), 0.0);
        // one factor: curvature = max(CVR+, CVR-) when positive; the FX scalar divides by 1.5
        assertEquals(3e5, FrtbVegaCurvature.curvature(fx, List.of(new FrtbVegaCurvature.Cvr("EURJPY", "", 3e5, 1e5)),
                false).capital(), 1e-9);
        assertEquals(2e5, FrtbVegaCurvature.curvature(fx, List.of(new FrtbVegaCurvature.Cvr("EURJPY", "", 3e5, 1e5)),
                true).capital(), 1e-9);
        // two buckets that both lose nothing under the selected shock do not offset (psi)
        FrtbVegaCurvature.CurvResult r = FrtbVegaCurvature.curvature(FrtbVegaCurvature.RiskClass.GIRR, List.of(
                new FrtbVegaCurvature.Cvr("EUR", "", -1e5, -2e5), new FrtbVegaCurvature.Cvr("USD", "", -1e5, -3e5)),
                false);
        assertEquals(0.0, r.capital(), 0.0);
    }
}
