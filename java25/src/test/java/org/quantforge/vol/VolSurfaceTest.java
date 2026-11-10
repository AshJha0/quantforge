package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** Stage E1 and E7 against independent routes: substitution, price-based Dupire, hand cases, limits. */
class VolSurfaceTest {
    private static final Smile.Svi S1 = new Smile.Svi(0.02, 0.1, -0.4, 0.02, 0.2);
    private static final Smile.Svi S2 = new Smile.Svi(0.035, 0.11, -0.35, 0.03, 0.25);
    private static final List<Surfaces.Slice> SURFACE = List.of(new Surfaces.Slice(0.25, S1),
            new Surfaces.Slice(1.0, S2));

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    @Test
    void ssviSliceEqualsItsSviImage() {
        Smile.Ssvi ssvi = new Smile.Ssvi(-0.7, 1.2, 0.4);
        Smile.Svi svi = Surfaces.ssviToSvi(-0.7, 1.2, 0.4, 0.04);
        for (double k = -1.0; k <= 1.0; k += 0.125) {
            assertEquals(ssvi.w(k, 0.04), svi.w(k), 1e-15);
        }
        assertEquals("E_DOMAIN", code(() -> Surfaces.ssviToSvi(-0.7, 1.2, 0.4, 0.0)));
        assertEquals("E_DOMAIN", code(() -> Surfaces.ssviToSvi(1.0, 1.2, 0.4, 0.04)));
    }

    @Test
    void dupireAgreesWithPriceBasedFiniteDifferences() {
        // local variance = 2 C_T / (K^2 C_KK) with F = 1, zero rates, so K = e^k
        double t = 0.6;
        double k = 0.05;
        double kk = Math.exp(k);
        double ht = 1e-4;
        double hk = 1e-3;
        java.util.function.DoubleBinaryOperator c = (tt, strike) -> {
            double w = Surfaces.surface(SURFACE, tt, Math.log(strike))[0];
            return Black.lognormal(1.0, 1.0, strike, tt, 1.0, Math.sqrt(w / tt));
        };
        double ct = (c.applyAsDouble(t + ht, kk) - c.applyAsDouble(t - ht, kk)) / (2 * ht);
        double ckk = (c.applyAsDouble(t, kk + hk) - 2 * c.applyAsDouble(t, kk) + c.applyAsDouble(t, kk - hk))
                / (hk * hk);
        double lv = Surfaces.dupire(SURFACE, new double[] {t}, new double[] {k}).localVol()[0];
        assertEquals(Math.sqrt(2 * ct / (kk * kk * ckk)), lv, 1e-5);
    }

    @Test
    void surfaceIsFlatInVolOutsideTheSlicesAndRightHandAtNodes() {
        double k = 0.1;
        double[] early = Surfaces.surface(SURFACE, 0.1, k);
        assertEquals(S1.w(k) * 0.1 / 0.25, early[0], 1e-16);
        assertEquals(S1.w(k) / 0.25, early[3], 1e-16);
        double[] node = Surfaces.surface(SURFACE, 0.25, k);
        assertEquals((S2.w(k) - S1.w(k)) / 0.75, node[3], 1e-15);
        double[] late = Surfaces.surface(SURFACE, 3.0, k);
        assertEquals(S2.w(k) * 3.0, late[0], 1e-15);
    }

    @Test
    void checksAndLimits() {
        Smile.Svi steep = new Smile.Svi(0.02, 1.5, 0.5, 0.0, 0.2); // right slope 2.25 > 2
        Surfaces.Check c = Surfaces.check(List.of(new Surfaces.Slice(1.0, steep)), new double[] {0.0});
        assertEquals(List.of(new Surfaces.Wing(0, "RIGHT", "LEE")), c.wings());
        Surfaces.Check swapped = Surfaces.check(List.of(new Surfaces.Slice(0.25, S2), new Surfaces.Slice(1.0, S1)),
                new double[] {-0.2, 0.0, 0.2});
        assertEquals(3, swapped.calendar().size());
        assertTrue(!swapped.arbitrageFree());
        assertEquals("E_INPUT", code(() -> Surfaces.checkSlices(List.of())));
        assertEquals("E_INPUT", code(() -> Surfaces.checkGrid(new double[0])));
        assertEquals("E_INPUT", code(() -> Surfaces.checkGrid(new double[] {0.1, 0.1})));
        double[] big = new double[10_001];
        for (int i = 0; i < big.length; i++) {
            big[i] = i;
        }
        assertEquals("E_LIMIT", code(() -> Surfaces.checkGrid(big)));
        assertEquals("E_ARBITRAGE", code(() -> Surfaces.forwardVols(new double[] {1, 2}, new double[] {0.3, 0.2})));
        // dyadic values: 0.5^2 * 1 == 0.25^2 * 4 exactly, so the forward variance is exactly 0 (ruling E-A5)
        assertArrayEquals(new double[] {0.5, 0.0},
                Surfaces.forwardVols(new double[] {1, 4}, new double[] {0.5, 0.25}), 0.0);
    }

    @Test
    void garchHandCaseForecastAndFit() {
        Garch.Path p = Garch.path(new double[] {0.01, -0.02}, 1e-5, 0.1, 0.8, 2.5e-4);
        assertEquals(5.410998350356715, p.loglik(), 1e-12);
        assertEquals(2.26e-4, p.next(), 1e-18);
        Garch.Forecast f = Garch.forecast(1e-5, 0.1, 0.8, 2.26e-4, 5, 252);
        for (int h = 1; h <= 5; h++) {
            assertEquals(1e-4 + Math.pow(0.9, h - 1) * 1.26e-4, f.variances()[h - 1], 1e-18);
        }
        // the fit maximises: it beats the generating parameters on a simulated series
        java.util.Random rng = new java.util.Random(7);
        double[] r = new double[400];
        double v = 1e-4;
        for (int i = 0; i < r.length; i++) {
            r[i] = Math.sqrt(v) * rng.nextGaussian();
            v = 5e-6 + 0.08 * r[i] * r[i] + 0.87 * v;
        }
        double v0 = Garch.sampleVariance(r);
        double best = Garch.fit(r, v0);
        assertTrue(best >= Garch.path(r, 5e-6, 0.08, 0.87, v0).loglik());
        assertEquals("E_DOMAIN", code(() -> Garch.fit(new double[30], 1e-4)));
        assertEquals("E_DOMAIN", code(() -> Garch.checkParameters(0.0, 0.1, 0.1)));
    }

    @Test
    void nelderMeadFindsAQuadraticMinimum() {
        double[] x = Garch.nelderMead(z -> (z[0] - 1) * (z[0] - 1) + 3 * (z[1] + 2) * (z[1] + 2), new double[] {0, 0},
                0.5);
        assertEquals(1.0, x[0], 1e-6);
        assertEquals(-2.0, x[1], 1e-6);
    }

    @Test
    void varianceSwapStripTendsToFlatVolSquared() {
        // flat 20% smile, fine wide strip: fair variance close to 0.04
        int n = 400;
        double[] puts = new double[n];
        double[] calls = new double[n];
        for (int i = 0; i < n; i++) {
            puts[i] = 100.0 - 0.2 * i;
            calls[i] = 100.0 + 0.5 * i;
        }
        double fv = VarianceStrip.fairVariance(100.0, 0.03, 0.01, 1.0, puts, calls, k -> 0.2, 0.2);
        assertEquals(0.04, fv, 2e-4);
        assertEquals(0.0354273940952977, VarianceStrip.realizedVariance(
                new double[] {100, 101, 99.5, 100.25, 102, 101.5}, 252), 1e-15);
    }

    @Test
    void vixHandCaseAndRules() {
        List<VarianceStrip.Quote> strip = List.of(
                new VarianceStrip.Quote(110, 0.3, 0.5, 10.0, 11.0),
                new VarianceStrip.Quote(90, 10.5, 11.5, 0.5, 0.7),
                new VarianceStrip.Quote(95, 6.0, 6.6, 1.4, 1.6),
                new VarianceStrip.Quote(100, 2.9, 3.1, 2.9, 3.3),
                new VarianceStrip.Quote(105, 1.0, 1.2, 5.8, 6.6));
        VarianceStrip.Term t = VarianceStrip.term(43200, 0.0, strip);
        assertEquals(99.9, t.forward(), 1e-12);
        assertEquals(95.0, t.k0(), 0.0);
        assertEquals(0.08188158767696967, t.variance(), 1e-12);
        assertEquals(100 * Math.sqrt(t.variance()), VarianceStrip.index(43200, t, 50000, t), 1e-12);
        // two consecutive zero call bids above K0 stop the call side, leaving no OTM call (ruling E-B15)
        List<VarianceStrip.Quote> cut = List.of(
                new VarianceStrip.Quote(90, 10.5, 11.5, 0.5, 0.7),
                new VarianceStrip.Quote(95, 6.0, 6.6, 1.4, 1.6),
                new VarianceStrip.Quote(100, 0.0, 3.1, 2.9, 3.3),
                new VarianceStrip.Quote(105, 0.0, 1.2, 5.8, 6.6),
                new VarianceStrip.Quote(110, 0.3, 0.5, 10.0, 11.0));
        assertEquals("E_INPUT", code(() -> VarianceStrip.term(43200, 0.0, cut)));
        assertEquals("E_INPUT", code(() -> VarianceStrip.term(0, 0.0, strip)));
        assertEquals("E_INPUT", code(() -> VarianceStrip.term(10, 0.0, strip.subList(0, 2))));
        assertEquals("E_DOMAIN", code(() -> VarianceStrip.term(10, 0.0, List.of(
                new VarianceStrip.Quote(90, -1, 1, 0, 1), strip.get(2), strip.get(3)))));
        assertEquals("E_INPUT", code(() -> VarianceStrip.term(10, 0.0, List.of(
                new VarianceStrip.Quote(90, 2, 1, 0, 1), strip.get(2), strip.get(3)))));
    }
}
