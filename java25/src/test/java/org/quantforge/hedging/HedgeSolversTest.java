package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.hedging.HedgeRatios.Greek;
import org.quantforge.hedging.HedgeRatios.Instrument;
import org.quantforge.hedging.HedgeRatios.Market;
import org.quantforge.hedging.HedgeRatios.Position;

/** Hand-checked values and every validation path of the stage I hedge solvers, in the specification's order. */
class HedgeSolversTest {
    private static final double INF = Double.POSITIVE_INFINITY;
    private static final double[][] A = {{1.0, 0.5}, {0.3, 1.2}, {0.1, 0.6}};
    private static final double[] B = {-2.0, 1.5, -0.7};
    private static final double[] W = {1.0, 2.0, 0.5};

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    private static LeastSquaresHedge.Solution qp(double[][] a, double[] b, double[] w, double ridge, double[][] eq,
            double[] e, double[] lo, double[] hi, boolean minNorm) {
        return LeastSquaresHedge.solve(a, b, w, ridge, eq, e, lo, hi, minNorm);
    }

    @Test
    void squareSystemIsHedgedExactly() {
        double[][] a = {{2.0, 1.0}, {1.0, 3.0}};
        LeastSquaresHedge.Solution s = qp(a, new double[] {1.0, 2.0}, new double[] {1, 1}, 0, null, null, null, null,
                false);
        assertArrayEquals(new double[] {-0.2, -0.6}, s.x(), 1e-14);
        assertEquals(0.0, s.objective(), 1e-28);
        assertEquals(2, s.rank());
    }

    @Test
    void activeBoundsAreHitExactly() {
        LeastSquaresHedge.Solution free = qp(A, B, W, 0, null, null, null, null, false);
        double[] lo = {-INF, free.x()[1] + 0.25};
        LeastSquaresHedge.Solution s = qp(A, B, W, 0, null, null, lo, null, false);
        assertEquals(lo[1], s.x()[1], 0.0);
        LeastSquaresHedge.Solution fixed = qp(A, B, W, 0, null, null, new double[] {0.5, -INF},
                new double[] {0.5, INF}, false);
        assertEquals(0.5, fixed.x()[0], 0.0);
    }

    @Test
    void equalitiesFixingEveryPositionGiveRankZero() {
        double[][] eq = {{1, 0}, {1, 1}};
        LeastSquaresHedge.Solution s = qp(A, B, W, 0, eq, new double[] {1, 3}, null, null, false);
        assertArrayEquals(new double[] {1, 2}, s.x(), 1e-14);
        assertEquals(0, s.rank());
    }

    @Test
    void minNormSplitsDuplicatesAndLeavesAZeroColumnAtZero() {
        double[][] dup = {{1, 1}, {2, 2}};
        LeastSquaresHedge.Solution s = qp(dup, new double[] {1, 2}, new double[] {1, 1}, 0, null, null, null, null,
                true);
        assertEquals(s.x()[0], s.x()[1], 1e-14);
        assertEquals(-0.5, s.x()[0], 1e-13);
        assertEquals(1, s.rank());
        LeastSquaresHedge.Solution z = qp(new double[][] {{1, 0}, {2, 0}}, new double[] {1, 2}, new double[] {1, 1}, 0,
                null, null, null, null, true);
        assertEquals(0.0, z.x()[1], 0.0);
        assertEquals(-1.0, z.x()[0], 1e-13);
        LeastSquaresHedge.Solution withEq = qp(new double[][] {{1, 1, 0}, {0, 0, 1}}, new double[] {1, 1},
                new double[] {1, 1}, 0, new double[][] {{0, 0, 1}}, new double[] {2}, null, null, true);
        assertArrayEquals(new double[] {-0.5, -0.5, 2.0}, withEq.x(), 1e-13);
        assertEquals(1, withEq.rank());
    }

    @Test
    void ridgeMakesASingularProblemRegular() {
        LeastSquaresHedge.Solution s = qp(new double[][] {{1, 1}}, new double[] {1}, new double[] {1}, 1.0, null, null,
                null, null, false);
        assertArrayEquals(new double[] {-1.0 / 3, -1.0 / 3}, s.x(), 1e-14);
    }

    @Test
    void qpChecksRunInTheSpecifiedOrder() {
        assertEquals("E_INPUT", code(() -> qp(new double[0][], new double[0], new double[0], 0, null, null, null, null,
                false)));
        assertEquals("E_INPUT", code(() -> qp(new double[][] {{1, 2}, {3}}, B, W, 0, null, null, null, null, false)));
        assertEquals("E_INPUT", code(() -> qp(A, new double[] {1}, W, 0, null, null, null, null, false)));
        assertEquals("E_INPUT", code(() -> qp(A, B, new double[] {1}, 0, null, null, null, null, false)));
        assertEquals("E_INPUT", code(() -> qp(A, B, W, 0, new double[][] {{1, 1}}, null, null, null, false)));
        assertEquals("E_INPUT", code(() -> qp(A, B, W, 0, new double[][] {{1}}, new double[] {1}, null, null, false)));
        assertEquals("E_INPUT", code(() -> qp(A, B, W, 0, new double[][] {{1, 1}}, new double[0], null, null, false)));
        assertEquals("E_INPUT", code(() -> qp(A, B, W, 0, null, null, new double[] {0}, null, false)));
        assertEquals("E_INPUT", code(() -> qp(A, B, W, 0, null, null, null, new double[] {0}, false)));
        assertEquals("E_INPUT", code(() -> qp(A, B, new double[] {0, 1, 1}, 0, null, null, new double[] {0, 0}, null,
                true)));
        assertEquals("E_DOMAIN", code(() -> qp(A, B, new double[] {0, 1, 1}, 0, null, null, null, null, false)));
        assertEquals("E_DOMAIN", code(() -> qp(A, B, W, -1, null, null, null, null, false)));
        assertEquals("E_DOMAIN", code(() -> qp(A, B, W, 0, null, null, new double[] {1, 0}, new double[] {0, 0},
                false)));
        assertEquals("E_SINGULAR", code(() -> qp(A, B, W, 0, new double[][] {{1, 0}, {0, 1}, {1, 1}},
                new double[] {0, 0, 0}, null, null, false)));
        assertEquals("E_SINGULAR", code(() -> qp(A, B, W, 0, new double[][] {{1, 1}, {2, 2}}, new double[] {0, 0},
                null, null, false)));
        assertEquals("E_SINGULAR", code(() -> qp(new double[][] {{1, 1}}, new double[] {1}, new double[] {1}, 0, null,
                null, null, null, false)));
        // Singular and infeasible together: E_SINGULAR first (I-14).
        assertEquals("E_SINGULAR", code(() -> qp(new double[][] {{1, 1}}, new double[] {1}, new double[] {1}, 0,
                new double[][] {{1, 1}}, new double[] {5}, new double[] {0, 0}, new double[] {1, 1}, false)));
    }

    @Test
    void infeasibleConstraintsAreRefused() {
        assertEquals("E_INFEASIBLE", code(() -> qp(A, B, W, 0, new double[][] {{1, 1}}, new double[] {3},
                new double[] {0, 0}, new double[] {1, 1}, false)));
        assertEquals("E_INFEASIBLE", code(() -> qp(A, B, W, 0, new double[][] {{1, 0}, {0, 1}}, new double[] {2, 0},
                new double[] {0, 0}, new double[] {1, 1}, false)));
        assertEquals("E_INFEASIBLE", code(() -> qp(A, B, W, 0, new double[][] {{1, -1}}, new double[] {0},
                new double[] {1, -INF}, new double[] {1, 0.5}, false)));
    }

    private static LeastSquaresHedge.IntegerSolution lots(double[][] a, double[] b, double[] sizes, double[] lo,
            double[] hi) {
        double[] w = new double[a.length];
        java.util.Arrays.fill(w, 1.0);
        return LeastSquaresHedge.solveLots(a, b, w, 0.0, sizes, lo, hi);
    }

    @Test
    void integerTiesFollowRulingI7() {
        // f(n) = (n + 0.5)^2: 0 and -1 tie exactly; the smaller sum |n| wins.
        assertArrayEquals(new long[] {0}, lots(new double[][] {{1}}, new double[] {0.5}, new double[] {1}, null, null)
                .lots());
        // f(n) = (n - 1.5)^2: 1 and 2 tie; 1 wins.
        assertArrayEquals(new long[] {1}, lots(new double[][] {{1}}, new double[] {-1.5}, new double[] {1}, null, null)
                .lots());
        // Two identical-cost choices with equal sum |n|: (0, 1) beats (1, 0) lexicographically.
        LeastSquaresHedge.IntegerSolution s = lots(new double[][] {{1, 0}, {0, 1}, {1, 1}},
                new double[] {-0.5, -0.5, -1.0}, new double[] {1, 1}, null, null);
        assertArrayEquals(new long[] {0, 1}, s.lots());
    }

    @Test
    void integerBoundsBindAndRoundingCostIsNonNegative() {
        LeastSquaresHedge.IntegerSolution s = lots(new double[][] {{250}}, new double[] {-1000.0},
                new double[] {1}, new double[] {-INF}, new double[] {2});
        assertArrayEquals(new long[] {2}, s.lots());
        assertEquals(500.0 * 500.0, s.objective(), 0.0);
        assertEquals(s.objective(), s.continuousObjective(), 1e-9);
        assertEquals(0.0, s.roundingCost(), 1e-9);
        LeastSquaresHedge.IntegerSolution z = lots(new double[][] {{1, 2}, {3, 4}}, new double[] {0, 0},
                new double[] {1, 1}, null, null);
        assertArrayEquals(new long[] {0, 0}, z.lots());
        assertEquals(0.0, z.objective(), 0.0);
    }

    @Test
    void integerChecks() {
        double[][] a = {{1, 0}, {0, 1}};
        double[] b = {1, 1};
        assertEquals("E_INPUT", code(() -> lots(a, b, new double[] {1}, null, null)));
        assertEquals("E_INPUT", code(() -> lots(a, b, new double[] {1, 1}, new double[] {0}, null)));
        assertEquals("E_INPUT", code(() -> lots(a, b, new double[] {1, 1}, null, new double[] {0})));
        assertEquals("E_DOMAIN", code(() -> lots(a, b, new double[] {1, 0}, null, null)));
        assertEquals("E_DOMAIN", code(() -> lots(a, b, new double[] {1, 1}, new double[] {2, 0},
                new double[] {1, 0})));
        assertEquals("E_DOMAIN", code(() -> LeastSquaresHedge.solveLots(a, b, new double[] {1, -1}, 0,
                new double[] {1, 1}, null, null)));
        assertEquals("E_SINGULAR", code(() -> lots(new double[][] {{1, 1}, {2, 2}}, b, new double[] {1, 1},
                new double[] {-1, -1}, new double[] {1, 1})));
    }

    @Test
    void roundHalfAwayFromZero() {
        assertEquals(-3.0, LeastSquaresHedge.roundHalfAway(-2.5));
        assertEquals(3.0, LeastSquaresHedge.roundHalfAway(2.5));
        assertEquals(2.0, LeastSquaresHedge.roundHalfAway(2.4999999999999996));
        assertEquals(0.0, LeastSquaresHedge.roundHalfAway(-0.3));
        assertEquals(Double.doubleToLongBits(0.0), Double.doubleToLongBits(LeastSquaresHedge.roundHalfAway(-0.3)));
    }

    @Test
    void minimumVarianceSingleHedgeIsMinusRhoSigmaRatio() {
        double ss = 0.02;
        double sf = 0.03;
        double rho = 0.9;
        double[][] s = {{ss * ss, rho * ss * sf}, {rho * ss * sf, sf * sf}};
        HedgeRatios.MinVariance mv = HedgeRatios.minimumVariance(s);
        assertEquals(-rho * ss / sf, mv.hedge()[0], 1e-15);
        assertEquals(rho * rho, mv.effectiveness(), 1e-14);
    }

    @Test
    void minimumVarianceChecks() {
        assertEquals("E_INPUT", code(() -> HedgeRatios.minimumVariance(new double[][] {{1}})));
        assertEquals("E_INPUT", code(() -> HedgeRatios.minimumVariance(new double[][] {{1, 0}, {0}})));
        assertEquals("E_INPUT", code(() -> HedgeRatios.minimumVariance(new double[][] {{1, 0.5}, {0.4, 1}})));
        assertEquals("E_DOMAIN", code(() -> HedgeRatios.minimumVariance(new double[][] {{0, 0}, {0, 1}})));
        assertEquals("E_SINGULAR", code(() -> HedgeRatios.minimumVariance(new double[][] {{1, 0}, {0, 0}})));
        assertEquals("E_SINGULAR", code(() -> HedgeRatios.minimumVariance(
                new double[][] {{1, 0.5, 0.5}, {0.5, 1, 1}, {0.5, 1, 1}})));
        assertEquals("E_NOT_POSITIVE_DEFINITE", code(() -> HedgeRatios.minimumVariance(
                new double[][] {{1, 2}, {2, 1}})));
        assertEquals("E_INPUT", code(() -> HedgeRatios.sampleCovariance(new double[] {1, 2, 3}, new double[0][])));
        assertEquals("E_INPUT", code(() -> HedgeRatios.sampleCovariance(new double[] {1, 2, 3},
                new double[][] {{1, 2}})));
        assertEquals("E_INPUT", code(() -> HedgeRatios.sampleCovariance(new double[] {1, 2},
                new double[][] {{1, 2}})));
    }

    private static double bsm(Market mk, Instrument kind, double k, double t, double spot, double vol) {
        double d1 = (Math.log(spot / k) + (mk.rate() - mk.dividendYield() + 0.5 * vol * vol) * t) / (vol * Math.sqrt(t));
        double d2 = d1 - vol * Math.sqrt(t);
        double fwd = spot * Math.exp(-mk.dividendYield() * t);
        double df = Math.exp(-mk.rate() * t);
        return kind == Instrument.CALL ? fwd * Normal.cdf(d1) - k * df * Normal.cdf(d2)
                : k * df * Normal.cdf(-d2) - fwd * Normal.cdf(-d1);
    }

    @Test
    void greeksMatchFiniteDifferencesOfThePrice() {
        Market mk = new Market(100, 0.03, 0.02, 0.25);
        for (Instrument kind : List.of(Instrument.CALL, Instrument.PUT)) {
            double[] g = HedgeRatios.greeks(mk, new Position(kind, 95.0, 1.5, 1));
            double h = 1e-3;
            double up = bsm(mk, kind, 95, 1.5, 100 + h, 0.25);
            double mid = bsm(mk, kind, 95, 1.5, 100, 0.25);
            double dn = bsm(mk, kind, 95, 1.5, 100 - h, 0.25);
            assertEquals((up - dn) / (2 * h), g[0], 1e-8);
            assertEquals((up - 2 * mid + dn) / (h * h), g[1], 1e-5);
            double hv = 1e-5;
            assertEquals((bsm(mk, kind, 95, 1.5, 100, 0.25 + hv) - bsm(mk, kind, 95, 1.5, 100, 0.25 - hv)) / (2 * hv),
                    g[2], 1e-6);
        }
        assertArrayEquals(new double[] {1, 0, 0}, HedgeRatios.greeks(mk, new Position(Instrument.UNDERLYING, null,
                null, 1)), 0.0);
    }

    @Test
    void deltaHedgeWithTheUnderlying() {
        Market mk = new Market(100, 0.03, 0.02, 0.25);
        Position call = new Position(Instrument.CALL, 100.0, 1.0, 10);
        HedgeRatios.GreekHedge g = HedgeRatios.neutralise(mk, List.of(call),
                List.of(new Position(Instrument.UNDERLYING, null, null, 0)), List.of(Greek.DELTA));
        assertEquals(-10 * HedgeRatios.greeks(mk, call)[0], g.quantities()[0], 1e-14);
        assertEquals(0.0, g.after()[0], 1e-14);
        assertEquals(g.before()[1], g.after()[1], 0.0);
    }

    @Test
    void greekChecks() {
        Market mk = new Market(100, 0.03, 0.02, 0.25);
        Position u = new Position(Instrument.UNDERLYING, null, null, 1);
        Position c = new Position(Instrument.CALL, 100.0, 1.0, 1);
        List<Position> book = List.of(c);
        assertEquals("E_INPUT", code(() -> HedgeRatios.neutralise(mk, book,
                List.of(new Position(Instrument.UNDERLYING, 1.0, null, 0)), List.of(Greek.DELTA))));
        assertEquals("E_INPUT", code(() -> HedgeRatios.neutralise(mk, List.of(new Position(Instrument.PUT, 1.0, null,
                1)), List.of(u), List.of(Greek.DELTA))));
        assertEquals("E_INPUT", code(() -> HedgeRatios.neutralise(mk, book, List.of(), List.of())));
        assertEquals("E_INPUT", code(() -> HedgeRatios.neutralise(mk, book, List.of(u, c), List.of(Greek.DELTA))));
        assertEquals("E_INPUT", code(() -> HedgeRatios.neutralise(mk, book, List.of(u, c),
                List.of(Greek.DELTA, Greek.DELTA))));
        assertEquals("E_DOMAIN", code(() -> HedgeRatios.neutralise(new Market(0, 0, 0, 0.2), book, List.of(u),
                List.of(Greek.DELTA))));
        assertEquals("E_DOMAIN", code(() -> HedgeRatios.neutralise(new Market(100, 0, 0, 0), book, List.of(u),
                List.of(Greek.DELTA))));
        assertEquals("E_DOMAIN", code(() -> HedgeRatios.neutralise(mk, List.of(new Position(Instrument.CALL, -1.0,
                1.0, 1)), List.of(u), List.of(Greek.DELTA))));
        assertEquals("E_DOMAIN", code(() -> HedgeRatios.neutralise(mk, List.of(new Position(Instrument.CALL, 1.0,
                0.0, 1)), List.of(u), List.of(Greek.DELTA))));
        assertEquals("E_SINGULAR", code(() -> HedgeRatios.neutralise(mk, book, List.of(u, u),
                List.of(Greek.DELTA, Greek.GAMMA))));
    }

    @Test
    void hullBetaExampleAndRounding() {
        // Hull ch. 3: V = 5,050,000, beta 1.5, futures 1,010 x 250: 30 contracts short.
        HedgeRatios.BetaHedge h = HedgeRatios.betaFutures(5_050_000, 1.5, 0.0, 1010, 250, true);
        assertEquals(-30.0, h.contracts(), 1e-12);
        assertEquals(-30.0, h.contractsHeld(), 0.0);
        assertEquals(0.0, h.betaAfter(), 1e-12);
        HedgeRatios.BetaHedge half = HedgeRatios.betaFutures(1000, 1.0, 0.0, 100, 4, true);
        assertEquals(-2.5, half.contracts(), 0.0);
        assertEquals(-3.0, half.contractsHeld(), 0.0);
        assertEquals(-2.5, HedgeRatios.betaFutures(1000, 1.0, 0.0, 100, 4, false).contractsHeld(), 0.0);
        assertEquals("E_DOMAIN", code(() -> HedgeRatios.betaFutures(0, 1, 0, 1, 1, true)));
        assertEquals("E_DOMAIN", code(() -> HedgeRatios.betaFutures(1, 1, 0, 0, 1, true)));
        assertEquals("E_DOMAIN", code(() -> HedgeRatios.betaFutures(1, 1, 0, 1, -1, true)));
    }

    @Test
    void residualReportChecks() {
        double[][] a = {{1}, {0}};
        double[] b = {1, 1};
        double[][] s = {{1, 0}, {0, 1}};
        HedgeRatios.Residual r = HedgeRatios.residualReport(a, b, new double[] {-1}, s);
        assertArrayEquals(new double[] {0, 1}, r.residual(), 0.0);
        assertEquals(0.5, r.effectiveness(), 0.0);
        assertEquals(1.0, r.volatilityAfter(), 0.0);
        assertEquals("E_INPUT", code(() -> HedgeRatios.residualReport(new double[0][], b, new double[0], s)));
        assertEquals("E_INPUT", code(() -> HedgeRatios.residualReport(new double[][] {{1}, {1, 2}}, b,
                new double[] {1}, s)));
        assertEquals("E_INPUT", code(() -> HedgeRatios.residualReport(a, new double[] {1}, new double[] {1}, s)));
        assertEquals("E_INPUT", code(() -> HedgeRatios.residualReport(a, b, new double[] {1, 2}, s)));
        assertEquals("E_INPUT", code(() -> HedgeRatios.residualReport(a, b, new double[] {1}, new double[][] {{1}})));
        assertEquals("E_INPUT", code(() -> HedgeRatios.residualReport(a, b, new double[] {1},
                new double[][] {{1, 0.1}, {0, 1}})));
        assertEquals("E_NOT_POSITIVE_DEFINITE", code(() -> HedgeRatios.residualReport(a, b, new double[] {1},
                new double[][] {{1, 0}, {0, -1}})));
        assertEquals("E_DOMAIN", code(() -> HedgeRatios.residualReport(a, new double[] {0, 0}, new double[] {1}, s)));
    }
}
