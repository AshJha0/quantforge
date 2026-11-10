package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.quantforge.pricing.BondsGuardTest.NAN;
import static org.quantforge.pricing.BondsGuardTest.fails;
import static org.quantforge.pricing.BondsGuardTest.nan;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Normal;

/** Library-level guards and range edges of CreditOptions. */
class CreditOptionsGuardTest {
    static final LocalDate A = LocalDate.of(2026, 11, 6);
    static final LocalDate E = LocalDate.of(2027, 3, 20);
    static final LocalDate M = LocalDate.of(2032, 3, 20);

    @Test
    void finiteChecks() {
        nan("r", () -> CreditOptions.legs(A, E, M, NAN, 0.02, 0.4));
        nan("h", () -> CreditOptions.legs(A, E, M, 0.03, NAN, 0.4));
        nan("rec", () -> CreditOptions.legs(A, E, M, 0.03, 0.02, NAN));
        nan("h", () -> CreditOptions.checkOption(A, E, M, NAN, 0.4, 0.01));
        nan("rec", () -> CreditOptions.checkOption(A, E, M, 0.02, NAN, 0.01));
        nan("k", () -> CreditOptions.checkOption(A, E, M, 0.02, 0.4, NAN));
        nan("r", () -> CreditOptions.impliedVol(A, E, M, NAN, 0.02, 0.4, true, 0.012, 1e7, 1e4));
        nan("h", () -> CreditOptions.impliedVol(A, E, M, 0.03, NAN, 0.4, true, 0.012, 1e7, 1e4));
        nan("rec", () -> CreditOptions.impliedVol(A, E, M, 0.03, 0.02, NAN, true, 0.012, 1e7, 1e4));
        nan("k", () -> CreditOptions.impliedVol(A, E, M, 0.03, 0.02, 0.4, true, NAN, 1e7, 1e4));
        nan("n", () -> CreditOptions.impliedVol(A, E, M, 0.03, 0.02, 0.4, true, 0.012, NAN, 1e4));
        nan("premium", () -> CreditOptions.impliedVol(A, E, M, 0.03, 0.02, 0.4, true, 0.012, 1e7, NAN));
        String[] names = {"r", "h", "rec", "k", "c", "n", "vol"};
        for (int i = 0; i < names.length; i++) {
            double[] v = {0.03, 0.02, 0.4, 0.012, 0.01, 1e7, 0.5};
            v[i] = NAN;
            nan(names[i], () -> CreditOptions.indexOption(A, E, M, v[0], v[1], v[2], true, v[3], v[4], v[5], v[6]));
        }
        nan("p", () -> CreditOptions.inverseNormal(NAN));
        nan("h", () -> CreditOptions.bivariateNormal(NAN, 0, 0.3));
        nan("k", () -> CreditOptions.bivariateNormal(0, NAN, 0.3));
        nan("rho", () -> CreditOptions.bivariateNormal(0, 0, NAN));
        nan("x", () -> CreditOptions.bivariateStudent(NAN, 0, 0.3, 4));
        nan("y", () -> CreditOptions.bivariateStudent(0, NAN, 0.3, 4));
        nan("rho", () -> CreditOptions.bivariateStudent(0, 0, NAN, 4));
        nan("nu", () -> CreditOptions.bivariateStudent(0, 0, 0.3, NAN));
        CreditOptions.Copula g = CreditOptions.Copula.GAUSSIAN;
        nan("p1", () -> CreditOptions.jointDefault(g, NAN, 0.03, 0.2, 0));
        nan("p2", () -> CreditOptions.jointDefault(g, 0.02, NAN, 0.2, 0));
        nan("rho", () -> CreditOptions.jointDefault(g, 0.02, 0.03, NAN, 0));
        nan("nu", () -> CreditOptions.jointDefault(g, 0.02, 0.03, 0.2, NAN));
        nan("p", () -> CreditOptions.checkPool(NAN, 0.3, 0.4));
        nan("rho", () -> CreditOptions.checkPool(0.05, NAN, 0.4));
        nan("rec", () -> CreditOptions.checkPool(0.05, 0.3, NAN));
        nan("p", () -> CreditOptions.lossCdf(NAN, 0.3, 0.4, 0.01));
        nan("rho", () -> CreditOptions.lossCdf(0.05, NAN, 0.4, 0.01));
        nan("rec", () -> CreditOptions.lossCdf(0.05, 0.3, NAN, 0.01));
        nan("x", () -> CreditOptions.lossCdf(0.05, 0.3, 0.4, NAN));
    }

    @Test
    void rangeEdges() {
        CreditOptions.checkOption(A, E, M, 0.0, 0.0, 0.01);
        fails("E_DOMAIN", null, () -> CreditOptions.checkOption(A, E, M, 0.02, 1.0, 0.01));
        fails("E_DOMAIN", null, () -> CreditOptions.checkOption(A, E, M, 0.02, 0.4, 0.0));
        fails("E_DOMAIN", null, () -> CreditOptions.checkOption(A, E, M, -1e-300, 0.4, 0.01));
        CreditOptions.checkPool(0.05, 0.3, 0.0);
        for (double[] bad : new double[][] {{0, 0.3, 0.4}, {1, 0.3, 0.4}, {0.05, 0, 0.4}, {0.05, 1, 0.4},
                {0.05, 0.3, 1}, {0.05, 0.3, -1e-300}}) {
            fails("E_DOMAIN", null, () -> CreditOptions.checkPool(bad[0], bad[1], bad[2]));
        }
        assertTrue(Double.isFinite(CreditOptions.indexOption(A, E, M, 0.03, 0.02, 0.0, true, 0.012, 0.01, 1e7, 0.5)
                .price()));
        fails("E_DOMAIN", "recovery", () -> CreditOptions.indexOption(A, E, M, 0.03, 0.02, 1.0, true, 0.012, 0.01,
                1e7, 0.5));
        fails("E_DOMAIN", "hazard_rate", () -> CreditOptions.indexOption(A, E, M, 0.03, -1e-300, 0.4, true, 0.012,
                0.01, 1e7, 0.5));
        assertEquals(0.05, CreditOptions.expectedMin(0.05, 0.3, 1.0), 0.0);
        assertEquals(0.0, CreditOptions.expectedMin(0.05, 0.3, 0.0), 0.0);
        for (double x : new double[] {-4.2, -3.1, -0.4, 0.0, 1.234}) {
            assertEquals(x, CreditOptions.inverseNormal(Normal.cdf(x)), 1e-14 * Math.max(1, Math.abs(x)));
        }
    }

    @Test
    void impliedVolRangeAndRoundTrip() {
        for (boolean payer : new boolean[] {true, false}) {
            CreditOptions.Legs l = CreditOptions.legs(A, E, M, 0.03, 0.02, 0.4);
            double f = l.forward();
            double scale = 1e7 * l.annuity();
            double k = 0.012;
            double lower = scale * Math.max(payer ? f - k : k - f, 0.0);
            double upper = scale * (payer ? f : k);
            fails("E_DOMAIN", "premium", () -> CreditOptions.impliedVol(A, E, M, 0.03, 0.02, 0.4, payer, k, 1e7,
                    lower));
            fails("E_DOMAIN", "premium", () -> CreditOptions.impliedVol(A, E, M, 0.03, 0.02, 0.4, payer, k, 1e7,
                    upper));
            for (double vol : new double[] {0.05, 0.5, 3.0}) {
                double p = CreditOptions.price(A, E, M, 0.03, 0.02, 0.4, payer, k, 1e7, vol, true).price();
                assertEquals(vol, CreditOptions.impliedVol(A, E, M, 0.03, 0.02, 0.4, payer, k, 1e7, p),
                        1e-11 * vol);
            }
        }
    }
}
