package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.pricing.EquityForward;

class VolSmileTest {
    private static Black.Option b76(double phi, double k, double t, double f, double d) {
        return new Black.Option(Black.Model.BLACK_76, phi, k, t, f, 0, 0, d, 0);
    }

    @Test
    void forwardCarriesDividendsOnCarryFactor() {
        double f = EquityForward.flat(100, 0.04, 0.05, 1, new double[] {0.5}, new double[] {2});
        assertEquals(97.0149584, f, 1e-7);
    }

    @Test
    void parityRecoversForwardAndDiscount() {
        List<EquityForward.Quote> q = List.of(new EquityForward.Quote(90, 10.4, 10.6, 0.9, 1.1),
                new EquityForward.Quote(110, 0.9, 1.1, 10.4, 10.6));
        EquityForward.Parity p = EquityForward.parity(q, null);
        assertEquals(0.95, p.discountFactor(), 1e-12);
        assertEquals(100.0, p.forward(), 1e-9);
    }

    @Test
    void impliedVolRoundTripsAndParityHolds() {
        Black.Option call = b76(1, 110, 2, 100, 0.9);
        Black.Option put = b76(-1, 110, 2, 100, 0.9);
        double c = Black.price(call, 0.3);
        assertEquals(0.3, Black.implied(call, c), 1e-11);
        assertEquals(0.9 * (100 - 110), c - Black.price(put, 0.3), 1e-11);
        assertThrows(QfError.class, () -> Black.implied(call, 0.9 * 100));
    }

    @Test
    void analyticGreeksAgreeWithBumps() {
        for (Black.Model m : Black.Model.values()) {
            Black.Option o = new Black.Option(m, -1, 95, 1.5, 100, 0.03, 0.01, 0.97, 0);
            double v = m == Black.Model.BACHELIER ? 20 : 0.25;
            Greeks.Analytic a = Greeks.analytic(o, v);
            Greeks.Bumped b = Greeks.bumped(o, v);
            assertEquals(a.delta(), b.delta(), 2e-4 + 1e-4 * Math.abs(a.delta()));
            assertEquals(a.gamma(), b.gamma(), 2e-4 + 1e-4 * Math.abs(a.gamma()));
            assertEquals(a.vega(), b.vega(), 2e-4 + 1e-4 * Math.abs(a.vega()));
            assertEquals(a.vanna(), b.vanna(), 2e-4 + 1e-4 * Math.abs(a.vanna()));
            assertEquals(a.volga(), b.volga(), 2e-4 + 1e-4 * Math.abs(a.volga()));
        }
    }

    @Test
    void sviFitRecoversKnownTruth() {
        Smile.Svi truth = new Smile.Svi(0.02, 0.1, -0.4, 0.05, 0.2);
        double[] k = {-0.5, -0.3, -0.15, 0.0, 0.15, 0.3, 0.5};
        double[] w = new double[k.length];
        for (int i = 0; i < k.length; i++) {
            w[i] = truth.w(k[i]);
        }
        Smile.SviFit f = Smile.calibrateSvi(k, w, null);
        assertEquals(0.0, f.rmse(), 1e-9);
        assertEquals(truth.rho(), f.svi().rho(), 1e-6);
    }

    @Test
    void surfaceIsFlatVolOutsideItsGridAndFindsCalendarArbitrage() {
        Surface s = new Surface(new double[] {1, 2}, new double[] {-0.1, 0.1}, new double[][] {{0.3, 0.3}, {0.2, 0.2}});
        assertEquals(0.09 * 0.5, s.totalVariance(0.5, 5.0), 1e-15);
        assertEquals(0.04 * 3, s.totalVariance(3, 0.0), 1e-15);
        assertEquals(2, s.calendarViolations().size());
    }

    @Test
    void arbitrageFreeSabrConservesMassAndMean() {
        Sabr.Params p = new Sabr.Params(0.3, 0.5, -0.3, 0.4);
        Sabr.ArbFree r = Sabr.arbFree(1.0, 1.0, p, 400, 100, 100, new double[] {0.8, 1.0, 1.3});
        assertEquals(1.0, r.mass(), 1e-11);
        assertEquals(1.0, r.mean(), 1e-10);
        assertTrue(r.minDensity() >= 0.0);
        assertFalse(r.vols()[1] == null);
    }

    @Test
    void fitsWithOverflowingQuotesGiveAContractError() {
        double[] x = {60, 75, 90, 100, 110, 125, 150};
        double[] v = {2e300, 0.37, 0.327, 0.304, 0.287, 0.27, 0.262};
        QfError e = assertThrows(QfError.class, () -> Sabr.calibrate(100, 1, 0.5, x, v, null));
        assertEquals("E_NON_FINITE", e.code());
        double[] k = {-0.4, -0.2, 0.0, 0.2, 0.4};
        double[] w = {2e300, 0.05, 0.04, 0.05, 0.06};
        assertEquals("E_NON_FINITE", assertThrows(QfError.class, () -> Smile.calibrateSvi(k, w, null)).code());
    }

    @Test
    void haganAtTheMoneyWithoutVolOfVolIsAlphaForBetaOne() {
        assertEquals(0.2, Sabr.hagan(1.0, 1.0, 1.0, new Sabr.Params(0.2, 1.0, 0.0, 0.0)), 1e-14);
    }
}
