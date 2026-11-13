package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** Ruling R6-6.1: planted caps make the active-set and integer searches return E_NO_CONVERGENCE. */
class IterationCapTest {
    private static final double[][] A = {{1.0, 0.5, 0.2}, {0.3, 1.2, 0.4}, {0.1, 0.6, 1.5}, {0.8, 0.2, 0.9}};
    private static final double[] B = {-2.0, 1.5, -0.7, 0.9};
    private static final double[] W = {1.0, 2.0, 0.5, 1.5};

    @AfterEach
    void reset() {
        LeastSquaresHedge.capOverride = -1;
        LeastSquaresHedge.nodeCapOverride = -1;
    }

    @Test
    void defaultCapIsTenNPlusHundred() {
        assertEquals(130, LeastSquaresHedge.iterationCap(3));
    }

    @Test
    void boundedSolveWithCapZeroDoesNotConverge() {
        LeastSquaresHedge.capOverride = 0;
        double[] lo = {0.0, 0.0, 0.0};
        double[] hi = {0.1, 0.1, 0.1};
        QfError e = assertThrows(QfError.class,
                () -> LeastSquaresHedge.solve(A, B, W, 0.0, null, null, lo, hi, false));
        assertEquals("E_NO_CONVERGENCE", e.code());
    }

    @Test
    void integerSearchWithNodeCapOneDoesNotConverge() {
        LeastSquaresHedge.nodeCapOverride = 1;
        QfError e = assertThrows(QfError.class, () -> LeastSquaresHedge.solveLots(A, B, W, 0.0,
                new double[] {1.0, 1.0, 1.0}, null, null));
        assertEquals("E_NO_CONVERGENCE", e.code());
    }
}
