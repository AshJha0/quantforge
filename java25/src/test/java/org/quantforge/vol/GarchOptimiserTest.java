package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** The GARCH optimiser on problems that need every Nelder-Mead move, and the fit against an exhaustive search. */
class GarchOptimiserTest {
    @Test
    void nelderMeadSolvesRosenbrockFromAFarStartWithASmallStep() {
        // a curved valley: reflection, expansion, both contractions and shrinks are all needed
        double[] x = Garch.nelderMead(z -> 100 * Math.pow(z[1] - z[0] * z[0], 2) + Math.pow(1 - z[0], 2),
                new double[] {-1.9, 2.0}, 0.05);
        assertEquals(1.0, x[0], 1e-5);
        assertEquals(1.0, x[1], 1e-5);
    }

    @Test
    void nelderMeadHandlesAThreeDimensionalIllScaledBowl() {
        double[] x = Garch.nelderMead(z -> 1e4 * (z[0] - 0.3) * (z[0] - 0.3) + (z[1] + 2) * (z[1] + 2)
                + 1e-2 * (z[2] - 5) * (z[2] - 5), new double[] {0, 0, 0}, 0.5);
        assertEquals(0.3, x[0], 1e-6);
        assertEquals(-2.0, x[1], 1e-5);
        assertEquals(5.0, x[2], 1e-3);
    }

    @Test
    void nelderMeadShrinksWhenReflectionAndContractionBothFail() {
        // flat at 1 outside a small pit around the start: only the shrink step brings the other vertices in
        double[] x = Garch.nelderMead(z -> {
            double d = Math.hypot(z[0], z[1]);
            return d < 0.01 ? d : 1.0;
        }, new double[] {0.005, 0.005}, 0.5);
        assertEquals(0.0, Math.hypot(x[0], x[1]), 1e-6);
    }

    @Test
    void nelderMeadStopsAtAFlatStart() {
        double[] x = Garch.nelderMead(z -> 7.0, new double[] {1, 2}, 0.5);
        assertEquals(2, x.length);
        assertTrue(Double.isFinite(x[0]) && Double.isFinite(x[1]));
    }

    @Test
    void fitMatchesAGridSearchToTheLastDigits() {
        java.util.Random rng = new java.util.Random(11);
        double[] r = new double[300];
        double v = 1e-4;
        for (int i = 0; i < r.length; i++) {
            r[i] = Math.sqrt(v) * rng.nextGaussian();
            v = 4e-6 + 0.1 * r[i] * r[i] + 0.85 * v;
        }
        double v0 = Garch.sampleVariance(r);
        double best = Garch.fit(r, v0);
        // an independent route: a fine grid over (alpha, beta), omega by golden section on each point
        double grid = Double.NEGATIVE_INFINITY;
        for (double a = 0.02; a <= 0.3; a += 0.005) {
            for (double b = 0.5; a + b < 0.995; b += 0.005) {
                double aa = a;
                double bb = b;
                double lo = Math.log(1e-8);
                double hi = Math.log(1e-3);
                for (int k = 0; k < 80; k++) {
                    double m1 = lo + (hi - lo) * 0.381966;
                    double m2 = hi - (hi - lo) * 0.381966;
                    if (Garch.path(r, Math.exp(m1), aa, bb, v0).loglik() < Garch.path(r, Math.exp(m2), aa, bb, v0)
                            .loglik()) {
                        lo = m1;
                    } else {
                        hi = m2;
                    }
                }
                grid = Math.max(grid, Garch.path(r, Math.exp(lo), aa, bb, v0).loglik());
            }
        }
        assertTrue(best >= grid - 1e-9, best + " below grid " + grid);
        assertTrue(best - grid < 0.05); // the grid is close, so the fit is not a wild value
    }

    /** Best log-likelihood over (alpha, beta) in hundredths with alpha + beta at most {@code capPercent}/100,
     * omega by golden section. */
    private static double gridBest(double[] r, double v0, int capPercent) {
        double best = Double.NEGATIVE_INFINITY;
        for (int i = 1; i <= 60; i++) {
            for (int j = 0; i + j <= capPercent; j++) {
                double a = i / 100.0;
                double b = j / 100.0;
                double lo = Math.log(1e-10);
                double hi = Math.log(1e-2);
                for (int k = 0; k < 60; k++) {
                    double m1 = lo + (hi - lo) * 0.381966;
                    double m2 = hi - (hi - lo) * 0.381966;
                    if (Garch.path(r, Math.exp(m1), a, b, v0).loglik() < Garch.path(r, Math.exp(m2), a, b, v0).loglik()) {
                        lo = m1;
                    } else {
                        hi = m2;
                    }
                }
                best = Math.max(best, Garch.path(r, Math.exp(lo), a, b, v0).loglik());
            }
        }
        return best;
    }

    @Test
    void fitStaysInsideTheStationaryRegion() {
        // variance grows 2% a step: the likelihood prefers alpha + beta above 1, which the fit must not reach
        java.util.Random rng = new java.util.Random(5);
        double[] r = new double[300];
        for (int i = 0; i < r.length; i++) {
            r[i] = Math.sqrt(1e-5 * Math.pow(1.02, i)) * rng.nextGaussian();
        }
        double v0 = r[0] * r[0] + 1e-6;
        // the stationary supremum is approached as alpha + beta -> 1, so the closed region bounds the fit
        double closed = gridBest(r, v0, 100);
        double outside = gridBest(r, v0, 160);
        // measured: closed 839.557, outside 843.259; a fit that escapes the constraint lands near the latter
        assertTrue(outside > closed + 2.0, "the series must reward non-stationary parameters");
        double fit = Garch.fit(r, v0);
        assertTrue(fit <= closed + 1.0, "fit " + fit + " left the stationary region (closed grid " + closed + ")");
    }

    @Test
    void fitRefusesZeroReturnsAndForecastIsFlatAtTheLongRunLevel() {
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> Garch.fit(new double[40], 1e-4)).code());
        Garch.Forecast f = Garch.forecast(1e-5, 0.1, 0.8, 1e-4, 3, 252);
        for (double x : f.variances()) {
            assertEquals(1e-4, x, 1e-18);
        }
        assertEquals(Math.sqrt(1e-4 * 252), f.annualizedVol(), 1e-15);
    }
}
