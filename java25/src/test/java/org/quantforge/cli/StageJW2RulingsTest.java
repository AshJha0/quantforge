package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collections;
import org.junit.jupiter.api.Test;
import org.quantforge.research.Allocation;

/** Rulings J-W2-17 to J-W2-22 (specifications/stage-j-rulings-w2.md). */
class StageJW2RulingsTest {
    private static String run(String op, String inputs) {
        return Main.handle("{\"schema_version\":\"1.0\",\"case_id\":\"c\",\"operation\":\"" + op
                + "\",\"inputs\":" + inputs + "}").json();
    }

    private static String row(int n) {
        return "[" + String.join(",", Collections.nCopies(n, "0.0")) + "]";
    }

    private static boolean limit(String r) {
        return r.contains("\"code\":\"E_LIMIT\"");
    }

    @Test
    void jw2_17RaggedMatrixWidthCounts() {
        String r = run("research.portfolio.mean_variance", "{\"expected_returns\":[0.1,0.1,0.1],\"covariance\":[[1,0,0],"
                + row(501) + ",[0,0,1]],\"risk_aversion\":1.0}");
        assertTrue(limit(r), r);
    }

    @Test
    void jw2_18KIsTheLongestInput() {
        String base = "{\"observations\":[0.1,0.2],\"initial\":[0.5,0.5],\"sds\":[1.0,1.0],";
        assertTrue(limit(run("research.regime.baum_welch", base + "\"transition\":[[0.5,0.5],[0.5,0.5]],\"means\":"
                + row(17) + "}")));
        assertTrue(limit(run("research.regime.baum_welch", base + "\"transition\":[[0.5,0.5]," + row(17)
                + "],\"means\":[0.0,1.0]}")));
    }

    @Test
    void jw2_19DefaultBudgetsAreNotSumTested() {
        double[][] s = new double[7][7];
        for (int i = 0; i < 7; i++) {
            for (int j = 0; j < 7; j++) {
                s[i][j] = i == j ? 1.0 : 0.1;
            }
        }
        for (double w : Allocation.riskParity(s, null).weights()) {
            assertEquals(1.0 / 7, w, 1e-10);
        }
    }

    @Test
    void jw2_20AllWeightsAtBoundStart() {
        double[][] s = {{0.04, 0.01, 0.0}, {0.01, 0.09, 0.02}, {0.0, 0.02, 0.16}};
        Allocation.MeanVariance r = Allocation.meanVariance(new double[] {0.3, 0.1, 0.2}, s, 2.0,
                new double[] {0.2, 0.3, 0.5}, new double[] {1, 1, 1});
        assertArrayEquals(new double[] {0.2, 0.3, 0.5}, r.weights(), 0.0);
        assertArrayEquals(new long[] {-1, -1, -1}, r.atBound());
    }

    @Test
    void jw2_21DegenerateProblemTerminates() {
        double[][] eye2 = {{1, 0}, {0, 1}};
        Allocation.MeanVariance r = Allocation.meanVariance(new double[] {0.1, 0.1}, eye2, 1.0, new double[] {0, 0},
                new double[] {0.5, 0.5});
        assertArrayEquals(new double[] {0.5, 0.5}, r.weights(), 0.0);
        double[][] eye3 = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};
        r = Allocation.meanVariance(new double[] {0.1, 0.9, 0.1}, eye3, 1.0, new double[] {0, 0.3, 0},
                new double[] {1, 0.3, 1});
        assertEquals(0.3, r.weights()[1], 0.0);
        assertEquals(-1, r.atBound()[1]);
    }

    @Test
    void jw2_22LedoitWolfSizes() {
        assertTrue(limit(run("research.estimate.ledoit_wolf", "{\"returns\":[[0,0]," + row(501) + "]}")));
        assertFalse(limit(run("research.estimate.ledoit_wolf", "{\"returns\":[[0,0]," + row(500) + "]}")));
        String rows = String.join(",", Collections.nCopies(20_001, "[0.0]"));
        assertTrue(limit(run("research.estimate.ledoit_wolf", "{\"returns\":[" + rows + "," + row(500) + "]}")));
    }
}
