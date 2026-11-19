package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.pricing.CreditOptions;

/**
 * Stage K wave 1 core (PROPOSED, KR-1 to KR-14): the acceptance tests the specs fixed (KR-4 correction property,
 * incremental-update property, trigger simulation, intraday bound on a seeded book) and the error paths. The golden
 * rows run through the CLI in GoldenSuiteTest and StageKCliTest.
 */
class StageKTest {
    private static final long DAY = 86_400;
    private static final long T0 = 1_767_225_600L; // 2026-01-01T00:00:00Z

    private static void code(String want, Runnable r) {
        QfError e = assertThrows(QfError.class, r::run);
        assertEquals(want, e.code(), e.getMessage());
    }

    private static double rel(double a, double b) {
        return Math.abs(a - b) / Math.max(Math.max(Math.abs(a), Math.abs(b)), 1e-300);
    }

    // --- bitemporal store ----------------------------------------------------------------------------

    private static StageK.BiRecord rec(long s, String id, long vf, Long vt, long kt, Object v, boolean del) {
        return new StageK.BiRecord(s, id, vf, vt, kt, v, del);
    }

    @Test
    void kr4CorrectionProperty10000Logs() {
        Random rnd = new Random(20261118);
        int checked = 0;
        for (int n = 0; n < 10_000; n++) {
            List<StageK.BiRecord> log = new ArrayList<>();
            long kt = 0;
            int len = 1 + rnd.nextInt(9);
            for (int s = 1; s < len; s++) {
                kt += rnd.nextInt(4) * DAY;
                long vf = T0 + rnd.nextInt(21) * DAY;
                Long vt = rnd.nextDouble() < 0.3 ? null : vf + (1 + rnd.nextInt(10)) * DAY;
                log.add(rec(s, rnd.nextBoolean() ? "A" : "B", vf, vt, T0 + kt, (long) rnd.nextInt(100),
                        rnd.nextDouble() < 0.15));
            }
            long k = T0 + rnd.nextInt((int) (kt / DAY) + 3) * DAY + (rnd.nextBoolean() ? 0 : 43_200);
            long later = Math.max(T0 + kt, k + 1) + rnd.nextInt(3) * DAY;
            List<StageK.BiRecord> more = new ArrayList<>(log);
            more.add(rec(log.size() + 1, rnd.nextBoolean() ? "A" : "B", T0 + rnd.nextInt(21) * DAY, null, later, -1L,
                    false));
            for (int vd = 0; vd < 25; vd++) {
                for (String series : new String[] {"A", "B"}) {
                    assertEquals(StageK.bitemporalQuery(log, series, k, T0 + vd * DAY),
                            StageK.bitemporalQuery(more, series, k, T0 + vd * DAY));
                    checked++;
                }
            }
        }
        assertEquals(500_000, checked);
    }

    @Test
    void withdrawnMasksAndStageAMapping() {
        StageK.BiRecord a = rec(1, "A", T0, null, T0, 1L, false);
        StageK.BiRecord d = rec(2, "A", T0, null, T0 + DAY, null, true);
        assertEquals("WITHDRAWN", StageK.bitemporalQuery(List.of(a, d), "A", T0 + DAY, T0).status());
        StageK.Answer f = StageK.bitemporalQuery(List.of(a, d), "A", T0, T0);
        assertEquals("FOUND", f.status());
        assertSame(a, f.row());
        StageK.BiRecord p = rec(1, "A", T0, T0 + 1, T0, 5L, false);
        assertEquals("NONE", StageK.bitemporalQuery(List.of(p), "A", T0, T0 + 1).status());
        assertNull(StageK.bitemporalQuery(List.of(p), "B", T0, T0).row());
    }

    @Test
    void logChecksAndLimit() {
        code("E_INPUT", () -> StageK.checkLog(List.of(rec(2, "A", T0, null, T0, 1L, false),
                rec(2, "A", T0, null, T0, 1L, false))));
        code("E_INPUT", () -> StageK.checkLog(List.of(rec(1, "A", T0, null, T0 + 1, 1L, false),
                rec(2, "A", T0, null, T0, 1L, false))));
        code("E_INPUT", () -> StageK.checkLog(List.of(rec(1, "A", T0, T0, T0, 1L, false))));
        code("E_DOMAIN", () -> StageK.bitemporalQuery(List.of(rec(1, "A", T0, null, T0, Double.NaN, false)), "A",
                T0, T0));
        assertEquals("FOUND", StageK.bitemporalQuery(List.of(rec(1, "A", T0, null, T0, 2.5, false)), "A", T0, T0)
                .status());
        List<StageK.BiRecord> big = new ArrayList<>(StageK.MAX_RECORDS + 1);
        for (int s = 1; s <= StageK.MAX_RECORDS + 1; s++) {
            big.add(rec(s, "A", T0, null, T0, 0L, false));
        }
        code("E_LIMIT", () -> StageK.bitemporalQuery(big, "A", T0, T0));
    }

    // --- bootstrap and incremental update ------------------------------------------------------------

    @Test
    void incrementalProperty10000Vectors() {
        Random rnd = new Random(20261118);
        for (int t = 0; t < 10_000; t++) {
            int n = 1 + rnd.nextInt(40);
            double[] old = new double[n];
            for (int i = 0; i < n; i++) {
                old[i] = -0.01 + 0.09 * rnd.nextDouble();
            }
            double[] neu = old.clone();
            List<Integer> idx = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                idx.add(i);
            }
            Collections.shuffle(idx, rnd);
            int moves = 1 + rnd.nextInt(Math.min(n, 4));
            for (int m = 0; m < moves; m++) {
                int j = idx.get(m);
                neu[j] = old[j] + 0.002 * rnd.nextGaussian();
            }
            double[] prev = StageK.parAnnual(old);
            StageK.Update up = StageK.incrementalUpdate(old, prev, neu);
            double[] full = StageK.parAnnual(neu);
            Integer j0 = up.firstChangedIndex();
            if (j0 == null) { // a normal draw of exactly zero cannot happen, but keep the branch honest
                assertArrayEquals(prev, up.discountFactors());
                continue;
            }
            for (int i = 0; i < j0; i++) {
                assertEquals(Double.doubleToRawLongBits(prev[i]), Double.doubleToRawLongBits(up.discountFactors()[i]));
            }
            for (int i = 0; i < n; i++) {
                assertTrue(rel(up.discountFactors()[i], full[i]) <= 1e-12);
            }
            assertArrayEquals(full, up.discountFactors()); // bit-identical to a full rebuild (KR-5)
            assertEquals(n - j0, up.recomputed());
        }
    }

    @Test
    void bootstrapErrors() {
        code("E_INPUT", () -> StageK.parAnnual(new double[0]));
        code("E_DOMAIN", () -> StageK.parAnnual(new double[] {0.01, -1.0}));
        code("E_DOMAIN", () -> StageK.parAnnual(new double[] {Double.NaN}));
        code("E_LIMIT", () -> StageK.parAnnual(new double[StageK.MAX_QUOTES + 1]));
        double[] q = {0.02, 0.025, 0.03};
        double[] dfs = StageK.parAnnual(q);
        code("E_INPUT", () -> StageK.incrementalUpdate(q, dfs, new double[2]));
        code("E_INPUT", () -> StageK.incrementalUpdate(new double[0], new double[0], new double[0]));
        code("E_DOMAIN", () -> StageK.incrementalUpdate(q, dfs, new double[] {0.02, -2.0, 0.03}));
        code("E_DOMAIN", () -> StageK.incrementalUpdate(new double[] {-3, 0, 0}, dfs, q));
        code("E_DOMAIN", () -> StageK.incrementalUpdate(q, new double[] {1, Double.POSITIVE_INFINITY, 1}, q));
        double[] stale = dfs.clone();
        stale[2] = Math.nextUp(stale[2]);
        code("E_INPUT", () -> StageK.incrementalUpdate(q, stale, q));
        double[] negZero = {0.0};
        code("E_INPUT", () -> StageK.incrementalUpdate(negZero, new double[] {-1.0}, negZero));
        double[] big = new double[StageK.MAX_QUOTES + 1];
        code("E_LIMIT", () -> StageK.incrementalUpdate(big, StageK.bootstrapFrom(big, big, 0), big));
        StageK.Update same = StageK.incrementalUpdate(q, dfs, q.clone());
        assertNull(same.firstChangedIndex());
        assertEquals(0, same.recomputed());
        assertArrayEquals(dfs, same.discountFactors());
    }

    // --- trigger ------------------------------------------------------------------------------------

    @Test
    void triggerSimulationAcceptance() {
        // recalibration-triggers.md: 100,000 noise paths, window 250, k = 3, d = 1; fire rate inside the 99 %
        // interval of the Student-t predictive rate (binomial interval by the normal approximation here); a
        // 6-sigma planted move fires on at least 99.9 % of paths.
        Random rnd = new Random(20261118);
        int n = 100_000;
        int w = 250;
        double k = 3.0;
        int fires = 0;
        int planted = 0;
        double[] z = new double[w];
        for (int p = 0; p < n; p++) {
            for (int i = 0; i < w; i++) {
                z[i] = rnd.nextGaussian();
            }
            double next = rnd.nextGaussian();
            double sig = StageK.sampleSd(z);
            boolean fire = Math.abs(next) > k * sig;
            if (fire) {
                fires++;
            }
            if (6.0 > k * sig) {
                planted++;
            }
            if (p < 200) {
                assertEquals(fire, StageK.triggerCheck(z, 0.0, next, 1.0, k).fire());
            }
        }
        double centre = 2 * (1 - CreditOptions.studentCdf(k / Math.sqrt(1 + 1.0 / w), w - 1));
        double sd = Math.sqrt(n * centre * (1 - centre));
        assertTrue(Math.abs(fires - n * centre) <= 2.5758293035489 * sd + 1, fires + " vs " + n * centre);
        assertTrue(planted >= 0.999 * n);
    }

    @Test
    void triggerErrors() {
        double[] c = {1.0, -1.0, 1.0, -1.0};
        code("E_INPUT", () -> StageK.triggerCheck(new double[] {1.0}, 0, 0, 1, 3));
        code("E_DOMAIN", () -> StageK.triggerCheck(c, 0, Double.NaN, 1, 3));
        code("E_DOMAIN", () -> StageK.triggerCheck(c, 0, 0, 1, 0));
        code("E_DOMAIN", () -> StageK.triggerCheck(c, 0, 0, 0.5, 3));
        code("E_DOMAIN", () -> StageK.triggerCheck(new double[] {2, 2, 2}, 0, 0, 1, 3));
        double[] big = new double[StageK.MAX_CHANGES + 2];
        for (int i = 0; i < big.length; i++) {
            big[i] = i % 2;
        }
        code("E_LIMIT", () -> StageK.triggerCheck(big, 0, 0, 1, 3));
        code("E_DOMAIN", () -> StageK.triggerCheck(big, 0, 0, 1, -1)); // E_DOMAIN before E_LIMIT
        StageK.Trigger t = StageK.triggerCheck(c, 100, 104, 1, 3);
        assertTrue(t.fire());
        assertTrue(rel(t.falseAlarmRate(), 0.002699796063260189) <= 1e-14);
        assertFalse(StageK.triggerCheck(c, 100, 100 + t.threshold(), 1, 3).fire()); // strict
    }

    // --- intraday bound ------------------------------------------------------------------------------

    @Test
    void intradayBoundAcceptance1000Moves() {
        Random rnd = new Random(20261118);
        List<StageK.ZeroPosition> book = new ArrayList<>();
        for (int i = 0; i < 50; i++) {
            book.add(new StageK.ZeroPosition(-5e6 + 1e7 * rnd.nextDouble(), 0.1 + 29.9 * rnd.nextDouble(),
                    -0.01 + 0.09 * rnd.nextDouble()));
        }
        for (int m = 0; m < 1000; m++) {
            double h = -0.02 + 0.04 * rnd.nextDouble();
            StageK.Intraday r = StageK.deltaGammaBound(book, h);
            double err = Math.abs(r.estimatePnl() - StageK.zeroRevalue(book, h));
            assertTrue(err <= r.bound(), h + ": " + err + " > " + r.bound());
            assertEquals(StageK.LABEL, r.label());
        }
    }

    @Test
    void intradayErrors() {
        StageK.ZeroPosition p = new StageK.ZeroPosition(1, 1, 0);
        code("E_INPUT", () -> StageK.deltaGammaBound(List.of(), 0.01));
        code("E_DOMAIN", () -> StageK.deltaGammaBound(List.of(p), Double.NEGATIVE_INFINITY));
        code("E_DOMAIN", () -> StageK.deltaGammaBound(List.of(new StageK.ZeroPosition(Double.NaN, 1, 0)), 0));
        code("E_DOMAIN", () -> StageK.deltaGammaBound(List.of(new StageK.ZeroPosition(1, Double.NaN, 0)), 0));
        code("E_DOMAIN", () -> StageK.deltaGammaBound(List.of(new StageK.ZeroPosition(1, 1, Double.NaN)), 0));
        code("E_DOMAIN", () -> StageK.deltaGammaBound(List.of(new StageK.ZeroPosition(1, 0, 0)), 0));
        List<StageK.ZeroPosition> big = new ArrayList<>(Collections.nCopies(StageK.MAX_POSITIONS + 1, p));
        code("E_LIMIT", () -> StageK.deltaGammaBound(big, 0.01));
        big.set(big.size() - 1, new StageK.ZeroPosition(1, 0, 0));
        code("E_DOMAIN", () -> StageK.deltaGammaBound(big, 0.01));
        StageK.Intraday z = StageK.deltaGammaBound(List.of(p), 0.0);
        assertEquals(0.0, z.estimatePnl());
        assertEquals(0.0, z.bound());
    }

    // --- Richardson ----------------------------------------------------------------------------------

    @Test
    void richardsonPaths() {
        code("E_INPUT", () -> StageK.richardsonCheck(new double[] {1.0}, 2, 2));
        code("E_DOMAIN", () -> StageK.richardsonCheck(new double[] {1, 2, 3}, 2, 0));
        code("E_DOMAIN", () -> StageK.richardsonCheck(new double[] {1, 2, 3}, 1, 1));
        code("E_DOMAIN", () -> StageK.richardsonCheck(new double[] {1, Double.NaN, 3}, 2, 1));
        assertEquals("NON_MONOTONE", StageK.richardsonCheck(new double[] {1, 1, 1}, 2, 2).status());
        assertEquals("NON_MONOTONE", StageK.richardsonCheck(new double[] {1, 2, 1}, 2, 2).status());
        StageK.Richardson ok = StageK.richardsonCheck(new double[] {11, 10.25, 10.0625}, 2, 2);
        assertEquals("OK", ok.status());
        assertEquals(2.0, ok.observedOrder(), 1e-12);
        assertEquals(10.0, ok.extrapolated(), 1e-12);
        StageK.Richardson mis = StageK.richardsonCheck(new double[] {12, 11, 10.5}, 2, 2);
        assertEquals("ORDER_MISMATCH", mis.status());
        assertNull(mis.toMap().get("extrapolated"));
        assertEquals(1.0, (Double) mis.toMap().get("observed_order"), 1e-12);
    }
}
