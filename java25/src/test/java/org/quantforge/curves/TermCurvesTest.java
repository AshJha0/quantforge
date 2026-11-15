package org.quantforge.curves;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** Stage J curves lane property tests (rulings J-C-1 to J-C-9), on this build's own seeded data. */
class TermCurvesTest {
    private static final double[] FT = {0.25, 0.5, 1.0, 2.0};
    private static final double[] FZ = {0.040, 0.041, 0.0415, 0.042};
    private static final double[] NONE = {};

    @Test
    void quotesRoundTripAndForwardsChain() {
        Random rnd = new Random(31);
        for (int trial = 0; trial < 50; trial++) {
            int n = 1 + rnd.nextInt(6);
            double[] qt = new double[n];
            double[] qr = new double[n];
            for (int i = 0; i < n; i++) {
                qt[i] = 0.1 * (i + 1);
                qr[i] = -0.01 + 0.11 * rnd.nextDouble();
            }
            TermCurves.TermCurve r = TermCurves.termCurve(TermCurves.build(new double[] {1.0},
                    new double[] {0.03}, qt, qr, NONE, NONE), qt);
            double growth = 1;
            double prev = 0;
            for (int i = 0; i < n; i++) {
                assertEquals(qr[i], r.financingRate()[i], 1e-13);
                growth *= 1 + r.forwardFinancing()[i] * (qt[i] - prev);
                prev = qt[i];
                assertEquals(1.0, growth * r.financingDf()[i], 1e-14);
            }
            assertNull(r.borrowFee());
        }
    }

    @Test
    void flatInputsReduceToD22() {
        double r = 0.03;
        double s = 0.004;
        double b = 0.002;
        double t = 0.75;
        double[] repo = {(Math.exp((r + s) * 0.25) - 1) / 0.25, Math.exp(r + s) - 1};
        TermCurves.FinancingCurve c = TermCurves.build(new double[] {1.0}, new double[] {r},
                new double[] {0.25, 1.0}, repo, new double[] {1.0}, new double[] {b});
        assertEquals(100 * Math.exp((r + s - b) * t), TermCurves.forward(c, 100, t, NONE, NONE).forward(), 1e-12);
        assertEquals(s, TermCurves.termCurve(c, new double[] {0.5}).spread()[0], 1e-15);
    }

    @Test
    void borrowAndDividendsLowerTheForward() {
        TermCurves.FinancingCurve c0 = TermCurves.build(FT, FZ, new double[] {1.0}, new double[] {0.044}, NONE, NONE);
        TermCurves.FinancingCurve c1 = TermCurves.build(FT, FZ, new double[] {1.0}, new double[] {0.044},
                new double[] {1.0}, new double[] {0.01});
        double base = TermCurves.forward(c0, 50, 0.75, NONE, NONE).forward();
        assertTrue(TermCurves.forward(c1, 50, 0.75, NONE, NONE).forward() < base);
        assertTrue(TermCurves.forward(c0, 50, 0.75, new double[] {0.5}, new double[] {1.0}).forward() < base);
    }

    @Test
    void errors() {
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> TermCurves.build(FT, FZ, new double[] {0.5, 0.5},
                new double[] {0.04, 0.04}, NONE, NONE)).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> TermCurves.build(FT, FZ, new double[] {0.5},
                new double[] {0.04}, new double[] {0.5, 1.0}, new double[] {0.02, 0.001})).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> TermCurves.build(FT, FZ, new double[] {3.0},
                new double[] {0.04}, NONE, NONE)).code());
        TermCurves.FinancingCurve c = TermCurves.build(FT, FZ, new double[] {1.0}, new double[] {0.04}, NONE, NONE);
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> TermCurves.termCurve(c, new double[] {1.5})).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> TermCurves.forward(c, 10, 0.5, new double[] {0.1}, new double[] {20})).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> TermCurves.liquidity(1, 1e7, 0.02, 1, 0, 0, new double[] {1}, new double[] {1})).code());
    }

    @Test
    void liquidityMatchesStageHAndOptimumIsAMinimum() {
        TermCurves.LiquidityCurve o = TermCurves.liquidity(0, 1e7, 0.02, 1, 0.5, 0, new double[] {1e5},
                new double[] {1});
        assertEquals(0.002, o.impact()[0][0], 1e-17);
        assertNull(o.optimalHorizon());
        Random rnd = new Random(5);
        for (int trial = 0; trial < 50; trial++) {
            double d = 0.1 + 0.9 * rnd.nextDouble();
            double q = 1e3 + 1e7 * rnd.nextDouble();
            double z = 0.1 + 3 * rnd.nextDouble();
            TermCurves.LiquidityCurve r = TermCurves.liquidity(2, 1e7, 0.02, 1, d, z, new double[] {q},
                    new double[] {1});
            double h = r.optimalHorizon()[0];
            for (double k : new double[] {0.9, 1.1}) {
                double other = TermCurves.liquidity(2, 1e7, 0.02, 1, d, z, new double[] {q},
                        new double[] {h * k}).totalCost()[0][0];
                assertTrue(other >= r.minCost()[0] - 1e-15);
            }
        }
    }
}
