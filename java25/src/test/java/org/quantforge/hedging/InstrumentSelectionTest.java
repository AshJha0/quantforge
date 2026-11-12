package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Random;
import net.jqwik.api.Example;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.quantforge.core.QfError;

/** Wave 4c: the spec's property test, the tie rule and every validation path of instrument selection. */
class InstrumentSelectionTest {

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    @Property(tries = 60)
    void fullSelectionIsTheQpAnswerAndTheBestNeverRisesWithK(@ForAll long seed) {
        Random rnd = new Random(seed);
        int n = 1 + rnd.nextInt(5);
        int m = n + rnd.nextInt(3);
        double[][] a = new double[m][n];
        double[] b = new double[m];
        double[] w = new double[m];
        for (int i = 0; i < m; i++) {
            for (int j = 0; j < n; j++) {
                a[i][j] = rnd.nextGaussian();
            }
            b[i] = 5 * rnd.nextGaussian();
            w[i] = 0.2 + rnd.nextDouble();
        }
        double prev = Double.POSITIVE_INFINITY;
        for (int k = 1; k <= n; k++) {
            InstrumentSelection.Selection s = InstrumentSelection.select(a, b, w, 0.0, null, null, k, false);
            assertTrue(s.objective() <= prev * (1 + 1e-12) + 1e-12, "objective rose at K = " + k);
            assertTrue(s.selected().length <= k);
            prev = s.objective();
            if (k == n) {
                LeastSquaresHedge.Solution full = LeastSquaresHedge.solve(a, b, w, 0.0, null, null, null, null,
                        false);
                for (int j = 0; j < n; j++) {
                    assertEquals(full.x()[j], s.x()[j], 1e-9 * Math.max(1.0, Math.abs(full.x()[j])));
                }
            }
        }
    }

    @Example
    void tiesGoToTheSmallerSubsetThenTheLowerIndex() {
        // Two symmetric instruments: index 0 wins.
        double[][] sym = {{1, 0}, {0, 1}};
        InstrumentSelection.Selection s = InstrumentSelection.select(sym, new double[] {-1, -1},
                new double[] {1, 1}, 0, null, null, 1, false);
        assertArrayEquals(new int[] {0}, s.selected());
        assertEquals(0.0, s.x()[1], 0.0);
        // One instrument hedges exactly; adding a second cannot do better, so the single one wins.
        double[][] a = {{1, 1}, {1, 2}};
        InstrumentSelection.Selection t = InstrumentSelection.select(a, new double[] {-1, -1}, new double[] {1, 1},
                0, null, null, 2, false);
        assertArrayEquals(new int[] {0}, t.selected());
        assertEquals(0.0, t.objective(), 1e-28);
    }

    @Example
    void candidateSubsetCountsFollowRulingI53() {
        assertEquals(60_459, InstrumentSelection.candidateSubsets(20, 6));
        assertEquals(137_979, InstrumentSelection.candidateSubsets(20, 7));
        assertEquals((1L << 20) - 1, InstrumentSelection.candidateSubsets(20, 20));
        assertEquals(31, InstrumentSelection.candidateSubsets(5, 99));
        assertEquals(0, InstrumentSelection.candidateSubsets(5, 0));
        assertTrue(InstrumentSelection.candidateSubsets(20, 7) > InstrumentSelection.MAX_SUBSETS);
    }

    @Example
    void combinationsAreLexicographic() {
        assertEquals(10, InstrumentSelection.combinations(5, 2).size());
        assertArrayEquals(new int[] {0, 1}, InstrumentSelection.combinations(5, 2).get(0));
        assertArrayEquals(new int[] {3, 4}, InstrumentSelection.combinations(5, 2).get(9));
        assertArrayEquals(new int[] {0, 1, 2}, InstrumentSelection.combinations(3, 3).get(0));
    }

    @Example
    void checks() {
        double[][] a = {{1, 0.2}, {0.1, 1}, {0.3, 0.3}};
        double[] b = {1, 2, 3};
        double[] w = {1, 1, 1};
        assertEquals("E_INPUT", code(() -> InstrumentSelection.select(a, new double[] {1}, w, 0, null, null, 1,
                false)));
        assertEquals("E_DOMAIN", code(() -> InstrumentSelection.select(a, b, new double[] {1, -1, 1}, 0, null, null,
                1, false)));
        assertEquals("E_INPUT", code(() -> InstrumentSelection.select(a, b, w, 0, null, null, 0, false)));
        assertEquals("E_INPUT", code(() -> InstrumentSelection.select(a, b, w, 0, null, null, 3, false)));
        assertEquals("E_INPUT", code(() -> InstrumentSelection.select(a, b, w, 0, null, null, 1, true)));
        assertEquals("E_DOMAIN", code(() -> InstrumentSelection.select(a, b, w, 0, new double[] {0.5, -1}, null, 1,
                false)));
        assertEquals("E_DOMAIN", code(() -> InstrumentSelection.select(a, b, w, 0, null, new double[] {1, -0.5}, 1,
                false)));
        assertEquals("E_SINGULAR", code(() -> InstrumentSelection.select(new double[][] {{1, 1}, {2, 2}},
                new double[] {1, 2}, new double[] {1, 1}, 0, null, null, 1, false)));
        InstrumentSelection.Selection bounded = InstrumentSelection.select(a, b, w, 0, new double[] {0, 0}, null, 2,
                false);
        for (double x : bounded.x()) {
            assertTrue(x >= 0.0);
        }
    }
}
