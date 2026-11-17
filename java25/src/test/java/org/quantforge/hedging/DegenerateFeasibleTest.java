package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.hedging.LeastSquaresHedge.Costs;
import org.quantforge.hedging.LeastSquaresHedge.Solution;

/**
 * Degenerate but feasible problems: the feasible set is one point, or the margin is tight at a vertex, so more
 * constraints are active than the dimension allows. The v0.9.0 kill round found the first three (Java refused the
 * first with E_INFEASIBLE: Goldfarb-Idnani's certificate fired on a 1e-16 rounding gap). Answers are worked by hand;
 * the same cases are in the Python, C++ and Rust unit tests.
 */
class DegenerateFeasibleTest {
    private static final double INF = Double.POSITIVE_INFINITY;
    private static final double[][] I2 = {{1, 0}, {0, 1}};
    private static final double[][] I3 = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};
    private static final double[][] C1_A = {{1, 0, -1}, {-1, 2, -1}, {1, 1, 2}};
    private static final double[] C1_B = {-1, -1, -3};
    private static final double[][] C1_EQ = {{-1, 0, 1}, {-1, -1, 0}};
    private static final double[] C1_E = {-2, -1};

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    private static Solution solve(double[][] a, double[] b, double[][] eq, double[] e, double[] lo, double[] hi,
            Costs c) {
        double[] w = new double[a.length];
        java.util.Arrays.fill(w, 1.0);
        return LeastSquaresHedge.solve(a, b, w, 0.0, eq, e, lo, hi, false, c);
    }

    private static Costs margin(double[] spreads, double[] rates, double limit) {
        return new Costs(spreads, null, 1.0, rates, limit);
    }

    @Test
    void singlePointFromEqualitiesAndBounds() {
        // The equalities leave (t, 1 - t, t - 2); x0 >= 1, x1 >= 0, x2 <= -1 meet only at t = 1. A x + b = (1, -1, -4).
        Solution s = solve(C1_A, C1_B, C1_EQ, C1_E, new double[] {1, 0, -2}, new double[] {INF, 1, -1}, null);
        assertArrayEquals(new double[] {1, 0, -1}, s.x(), 1e-12);
        assertEquals(18.0, s.objective(), 18.0 * 1e-12);
        assertEquals(1, s.rank());
    }

    @Test
    void singlePointInfeasibleNeighbourStillRaises() {
        assertEquals("E_INFEASIBLE", code(() -> solve(C1_A, C1_B, C1_EQ, C1_E, new double[] {1, 0, -2},
                new double[] {INF, 1, -1.000001}, null)));
    }

    @Test
    void marginTightAtTheOnlyFeasiblePoint() {
        // x0 + x1 = 1 and |x0| + 4 |x1| <= 1 meet only at (1, 0).
        Solution s = solve(I2, new double[] {0, 0}, new double[][] {{1, 1}}, new double[] {1}, null, null,
                margin(null, new double[] {1, 4}, 1.0));
        assertArrayEquals(new double[] {1, 0}, s.x(), 1e-12);
        assertEquals(1.0, s.objective(), 1e-12);
        assertEquals(1.0, s.margin(), 1e-12);
        Solution c = solve(I2, new double[] {0, 0}, new double[][] {{1, 1}}, new double[] {1}, null, null,
                margin(new double[] {0.5, 0.5}, new double[] {1, 4}, 1.0));
        assertArrayEquals(new double[] {1, 0}, c.x(), 1e-12);
        assertEquals(1.0, c.risk(), 1e-12);
        assertEquals(0.5, c.cost(), 1e-12);
        assertEquals(1.5, c.objective(), 1e-12);
    }

    @Test
    void marginInfeasibleNeighbourStillRaises() {
        assertEquals("E_INFEASIBLE", code(() -> solve(I2, new double[] {0, 0}, new double[][] {{1, 1}},
                new double[] {1}, null, null, margin(null, new double[] {1, 4}, 0.999999))));
    }

    @Test
    void costedTwoEqualitiesAndAMargin() {
        // x = (t, 0, 1 + t), f(t) = (t + 4)^2 + (1 - 4t)^2 + 2 (t + 1)^2 + |t|, minimised at t = -3/38.
        double[][] a = {{-1, 1, 2}, {-2, -2, -2}, {-2, -1, 1}, {1, -1, 0}};
        Solution s = solve(a, new double[] {2, 3, -2, 1}, new double[][] {{-1, -1, 1}, {0, 1, 0}},
                new double[] {1, 0}, null, null, margin(new double[] {1, 1, 0}, new double[] {1, 2, 0}, 1.0));
        assertArrayEquals(new double[] {-3.0 / 38, 0, 35.0 / 38}, s.x(), 1e-12);
        assertEquals(3.0 / 38, s.cost(), 1e-12);
        assertEquals(27151.0 / 1444, s.risk(), 1e-11);
        assertEquals(27265.0 / 1444, s.objective(), 1e-11);
        assertEquals(3.0 / 38, s.margin(), 1e-12);
    }

    @Test
    void equalityRepeatsAFixedBound() {
        Solution s = solve(I2, new double[] {0, 0}, new double[][] {{1, 0}}, new double[] {1},
                new double[] {1, -INF}, new double[] {1, INF}, null);
        assertArrayEquals(new double[] {1, 0}, s.x(), 1e-12);
        assertEquals(1.0, s.objective(), 1e-12);
    }

    @Test
    void everyBoundFixed() {
        Solution s = solve(I2, new double[] {1, 1}, null, null, new double[] {0.5, -2}, new double[] {0.5, -2}, null);
        assertArrayEquals(new double[] {0.5, -2}, s.x(), 0.0);
        assertEquals(3.25, s.objective(), 1e-12);
    }

    @Test
    void singleVertexOfTheBox() {
        // sum x = 3 with x <= 1 is met only at (1, 1, 1); x0 = x1 is redundant there too.
        double[] hi = {1, 1, 1};
        Solution one = solve(I3, new double[3], new double[][] {{1, 1, 1}}, new double[] {3}, null, hi, null);
        assertArrayEquals(new double[] {1, 1, 1}, one.x(), 1e-12);
        assertEquals(3.0, one.objective(), 1e-12);
        Solution two = solve(I3, new double[3], new double[][] {{1, 1, 1}, {1, -1, 0}}, new double[] {3, 0}, null, hi,
                null);
        assertArrayEquals(new double[] {1, 1, 1}, two.x(), 1e-12);
        assertEquals(3.0, two.objective(), 1e-12);
    }

    @Test
    void boxVertexInfeasibleNeighbourStillRaises() {
        assertEquals("E_INFEASIBLE", code(() -> solve(I2, new double[] {0, 0}, new double[][] {{1, 1}},
                new double[] {2.000001}, null, new double[] {1, 1}, null)));
    }

    @Test
    void dependentRowAtADegenerateVertexDoesNotHideTheX2SignFlip() {
        // x0 >= 1 and 0.5 x0 + 0.5 |x1| <= 0.5 force x0 = 1, x1 = 0, where x1 >= 0 is -2 (margin) - (x0 >= 1): a row
        // dependent on the active set. A rounding-size back-solved coefficient (1e-18) taken as a blocking row dropped
        // the x2 sign row (C++ commit badcf1be). With x0 = 1, x1 = 0, f(x2) = 75.25 + 38 x2 + 44 x2^2 + |x2|, so
        // x2 = -37/88 and f = 75.25 - 37^2 / 176. Same case in the Python, C++ and Rust unit tests.
        double[][] a = {{3, 2, -2}, {-2, 7, 2}, {3, -1, 6}, {1, 0, 0}};
        double[] b = {-1, -3, 2.5, 3};
        Solution s = solve(a, b, null, null, new double[] {1, -1, -INF}, new double[] {2, INF, INF},
                margin(new double[] {0, 0.75, 1}, new double[] {0.5, 0.5, 0}, 0.5));
        double x2 = -37.0 / 88.0;
        double objective = 75.25 - 37.0 * 37.0 / 176.0;
        assertEquals(1.0, s.x()[0], 1e-12);
        assertEquals(0.0, s.x()[1], 1e-12);
        assertEquals(x2, s.x()[2], Math.abs(x2) * 1e-12);
        assertEquals(objective, s.objective(), objective * 1e-12);
    }
}
