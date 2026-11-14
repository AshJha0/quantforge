package org.quantforge.research;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import org.junit.jupiter.api.Test;

/** Stage J wave 1 property tests (STAGE_J_HANDOVER.md "Property tests"), on this build's own seeded data. */
class ResearchPropertyTest {

    private static double[] walk(Random r, int n, double drift) {
        double[] p = new double[n];
        p[0] = 100;
        for (int i = 1; i < n; i++) {
            p[i] = Math.max(1, p[i - 1] + drift + r.nextGaussian());
        }
        return p;
    }

    private static void close(double[] a, double[] b, double rel) {
        for (int i = 0; i < a.length; i++) {
            assertEquals(a[i], b[i], rel * Math.max(1, Math.abs(a[i])));
        }
    }

    @Test
    void eventEqualsVectorAndAttributionCloses() {
        Random r = new Random(11);
        for (int trial = 0; trial < 200; trial++) {
            int n = 2 + r.nextInt(60);
            double[] p = walk(r, n, 0);
            double[] tg = new double[n];
            for (int i = 0; i < n; i++) {
                tg[i] = r.nextInt(7) - 3;
            }
            int lag = r.nextInt(Math.min(n, 4));
            double hs = r.nextDouble() * 10;
            double c = r.nextDouble() * 0.05;
            double f = r.nextDouble();
            double m = 0.5 + r.nextDouble() * 50;
            Research.Backtest e = Research.backtest(p, tg, lag, hs, c, f, m, Research.Engine.EVENT);
            Research.Backtest v = Research.backtest(p, tg, lag, hs, c, f, m, Research.Engine.VECTOR);
            close(e.equity(), v.equity(), 1e-10);
            close(e.net(), v.net(), 1e-10);
            close(e.positions(), v.positions(), 1e-10);
            assertEquals(e.maxDrawdown(), v.maxDrawdown(), 1e-10 * Math.max(1, e.maxDrawdown()));
            assertEquals(e.tradeCount(), v.tradeCount());
            double big = Math.max(Math.max(Math.abs(e.totalGross()), e.totalSpread()),
                    Math.max(e.totalCommission(), e.totalFixed()));
            assertEquals(e.totalNet(),
                    e.totalGross() - e.totalSpread() - e.totalCommission() - e.totalFixed(), 1e-12 * Math.max(1, big));
            Research.Backtest zero = Research.backtest(p, tg, lag, 0, 0, 0, m, Research.Engine.EVENT);
            assertArrayEquals(zero.gross(), zero.net());
            Research.Backtest dbl = Research.backtest(p, tg, lag, 2 * hs, 2 * c, 2 * f, m, Research.Engine.EVENT);
            assertEquals(2 * e.totalSpread(), dbl.totalSpread(), 1e-12 * Math.max(1, e.totalSpread()));
            assertEquals(2 * e.totalCommission(), dbl.totalCommission(), 1e-12 * Math.max(1, e.totalCommission()));
            assertEquals(2 * e.totalFixed(), dbl.totalFixed(), 1e-12 * Math.max(1, e.totalFixed()));
        }
    }

    @Test
    void lookAheadCanaryCaughtAtLagZeroOnly() {
        Random r = new Random(7);
        int n = 2000;
        double[] p = walk(r, n, 0);
        double[] tg = new double[n];
        for (int t = 0; t + 1 < n; t++) {
            tg[t] = Math.signum(p[t + 1] - p[t]);
        }
        // at lag 0 the canary's position after close t earns bar t+1's move it peeked at
        double cheat = Research.backtest(p, tg, 0, 0, 0, 0, 1, Research.Engine.EVENT).totalGross();
        double honest = Research.backtest(p, tg, 1, 0, 0, 0, 1, Research.Engine.EVENT).totalGross();
        assertTrue(cheat > 0.5 * n, "canary detected at lag 0: " + cheat);
        assertTrue(Math.abs(honest) < 0.2 * cheat, "no edge at lag 1: " + honest);
    }

    @Test
    void purgedTrainNeverOverlapsAndPlainKFoldWhenNoLabelSpan() {
        Random r = new Random(3);
        for (int trial = 0; trial < 200; trial++) {
            int n = 2 + r.nextInt(80);
            double[] t0 = new double[n];
            double[] t1 = new double[n];
            for (int i = 0; i < n; i++) {
                t0[i] = i == 0 ? 0 : t0[i - 1] + r.nextInt(3);
                t1[i] = t0[i] + r.nextInt(6);
            }
            int k = 2 + r.nextInt(n - 1);
            double pct = r.nextDouble() * 0.3;
            for (Research.Fold f : Research.purgedKFold(t0, t1, k, pct).folds()) {
                int a = f.test().get(0).intValue();
                double lo = t0[a];
                double hi = Double.NEGATIVE_INFINITY;
                for (long i : f.test()) {
                    hi = Math.max(hi, t1[(int) i]);
                }
                for (long j : f.train()) {
                    assertFalse(t0[(int) j] <= hi && t1[(int) j] >= lo);
                    assertFalse(f.test().contains(j));
                }
            }
            Research.PurgedKFold plain = Research.purgedKFold(t0, t0, k, 0);
            int a = 0;
            for (int f = 0; f < k; f++) {
                int b = a + n / k + (f < n % k ? 1 : 0);
                List<Long> test = new ArrayList<>();
                List<Long> train = new ArrayList<>();
                for (int j = 0; j < n; j++) {
                    (j >= a && j < b ? test : train).add((long) j);
                }
                // equal start times outside the block would overlap a zero-width span; plain k-fold needs distinct t0
                boolean distinct = true;
                for (int j = 1; j < n; j++) {
                    distinct &= t0[j] != t0[j - 1];
                }
                if (distinct) {
                    assertEquals(test, plain.folds().get(f).test());
                    assertEquals(train, plain.folds().get(f).train());
                }
                a = b;
            }
        }
    }

    private static double[] row(Random r, int k) {
        double[] x = new double[k];
        double s = 0;
        for (int i = 0; i < k; i++) {
            x[i] = r.nextDouble() + 0.01;
            s += x[i];
        }
        for (int i = 0; i < k; i++) {
            x[i] /= s;
        }
        return x;
    }

    @Test
    void viterbiEqualsBruteForce() {
        Random r = new Random(5);
        for (int trial = 0; trial < 300; trial++) {
            int k = 1 + r.nextInt(3);
            int n = 1 + r.nextInt(6);
            double[] init = row(r, k);
            double[][] a = new double[k][];
            for (int i = 0; i < k; i++) {
                a[i] = row(r, k);
            }
            double[][] e = new double[n][k];
            for (int t = 0; t < n; t++) {
                for (int j = 0; j < k; j++) {
                    e[t][j] = r.nextDouble();
                }
            }
            Research.Viterbi v = Research.viterbi(init, a, Research.logEmission(e));
            int total = (int) Math.pow(k, n);
            double best = Double.NEGATIVE_INFINITY;
            int[] bestPath = null;
            for (int code = 0; code < total; code++) {
                int[] path = new int[n];
                int c = code;
                for (int t = n - 1; t >= 0; t--) {
                    path[t] = c % k;
                    c /= k;
                }
                double lp = Math.log(init[path[0]]) + Math.log(e[0][path[0]]);
                for (int t = 1; t < n; t++) {
                    lp += Math.log(a[path[t - 1]][path[t]]) + Math.log(e[t][path[t]]);
                }
                if (lp > best + 1e-12) {
                    best = lp;
                    bestPath = path;
                }
            }
            assertEquals(best, v.logProbability(), 1e-9);
            for (int t = 0; t < n; t++) {
                assertEquals(bestPath[t], v.states()[t]);
            }
        }
    }

    @Test
    void viterbiTiesTakeSmallestIndex() {
        double[] init = {0.5, 0.5};
        double[][] a = {{0.5, 0.5}, {0.5, 0.5}};
        double[][] e = {{0.3, 0.3}, {0.2, 0.2}};
        assertArrayEquals(new long[] {0, 0}, Research.viterbi(init, a, Research.logEmission(e)).states());
    }

    @Test
    void dsrDecreasingAndPsrHalfAtBenchmark() {
        double prev = 2;
        for (long n = 1; n <= 1000; n += 37) {
            double d = Research.dsr(0.1, 500, -0.5, 5, n, 0.002)[2];
            assertTrue(d <= prev);
            prev = d;
        }
        prev = 2;
        for (double var = 0; var < 0.01; var += 0.0005) {
            double d = Research.dsr(0.1, 500, -0.5, 5, 50, var)[2];
            assertTrue(d <= prev);
            prev = d;
        }
        assertEquals(0.5, Research.psr(0.07, 300, 0.3, 4, 0.07)[1], 1e-15);
        assertEquals(Research.psr(0.07, 300, 0.3, 4, 0)[1], Research.dsr(0.07, 300, 0.3, 4, 1, 0.5)[2], 0);
    }

    @Test
    void pboInUnitIntervalAndZeroWhenOneStrategyDominates() {
        Random r = new Random(9);
        for (int trial = 0; trial < 50; trial++) {
            int s = 2 * (1 + r.nextInt(4));
            int t = s * (2 + r.nextInt(4));
            int n = 2 + r.nextInt(6);
            double[][] perf = new double[t][n];
            for (int i = 0; i < t; i++) {
                for (int j = 0; j < n; j++) {
                    perf[i][j] = r.nextGaussian();
                }
            }
            double pbo = Research.pbo(perf, s, Research.Metric.SHARPE).pbo();
            assertTrue(pbo >= 0 && pbo <= 1);
            for (int i = 0; i < t; i++) {
                perf[i][n - 1] = 10 + Math.abs(perf[i][n - 1]);
            }
            assertEquals(0.0, Research.pbo(perf, s, Research.Metric.MEAN).pbo());
        }
    }
}
