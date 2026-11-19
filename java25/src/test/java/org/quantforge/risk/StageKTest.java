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

/**
 * Stage K wave 1 core (PROPOSED, KR-1 to KR-14): the acceptance tests the specs fixed (KR-4 correction property,
 * incremental-update property, trigger simulation (KR-232), intraday bound on a seeded book and the KR-234
 * small-move sweep) and the error paths in the HR-122 order (KR-230). The golden
 * rows run through the CLI in GoldenSuiteTest and StageKCliTest.
 */
class StageKTest {
    private static final long DAY = 86_400;
    private static final long T0 = 1_767_225_600L; // 2026-01-01T00:00:00Z

    private static void code(String want, Runnable r) {
        QfError e = assertThrows(QfError.class, r::run);
        assertEquals(want, e.code(), e.getMessage());
    }

    static void evidence(String key, String json) {
        StageKEvidence.write(key, json);
    }

    /** Smallest k with P(X <= k) >= q for X ~ Binomial(n, p): scipy.stats.binom.ppf, by the pmf recurrence. */
    static int binomPpf(int n, double p, double q) {
        double pmf = Math.exp(n * Math.log1p(-p));
        double cdf = pmf;
        int k = 0;
        while (cdf < q && k < n) {
            pmf *= (double) (n - k) / (k + 1) * p / (1 - p);
            k++;
            cdf += pmf;
        }
        return k;
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
        evidence("kr4_correction_property", "{\"logs\": 10000, \"queries_compared\": " + checked
                + ", \"failures\": 0, \"seed\": \"java.util.Random(20261118)\"}");
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
        double worst = 0;
        int bitEqual = 0;
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
            for (int i = 0; i < n; i++) {
                worst = Math.max(worst, rel(up.discountFactors()[i], full[i]));
            }
            assertArrayEquals(full, up.discountFactors()); // bit-identical to a full rebuild (KR-5)
            bitEqual++;
            assertEquals(n - j0, up.recomputed());
        }
        evidence("incremental_property", "{\"vectors\": 10000, \"max_relative_difference\": " + worst
                + ", \"bit_identical_to_full_rebuild\": " + bitEqual + ", \"copied_pillars_bit_identical\": true"
                + ", \"seed\": \"java.util.Random(20261118)\"}");
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
        // KR-230: E_LIMIT, the finite rule, structural E_INPUT, E_DOMAIN, stale-cache E_INPUT
        code("E_LIMIT", () -> StageK.incrementalUpdate(q, new double[] {Double.NaN}, big));
        code("E_DOMAIN", () -> StageK.incrementalUpdate(q, new double[] {Double.NaN}, new double[2]));
        code("E_INPUT", () -> StageK.incrementalUpdate(new double[] {-3, 0, 0}, dfs, new double[2]));
        double[] bigNan = new double[StageK.MAX_QUOTES + 1];
        bigNan[0] = Double.NaN;
        code("E_LIMIT", () -> StageK.parAnnual(bigNan));
        StageK.Update same = StageK.incrementalUpdate(q, dfs, q.clone());
        assertNull(same.firstChangedIndex());
        assertEquals(0, same.recomputed());
        assertArrayEquals(dfs, same.discountFactors());
    }

    // --- trigger ------------------------------------------------------------------------------------

    @Test
    void triggerSimulationAcceptance() {
        // KR-232 acceptance (replaces the window-250 simulation of the first version): for n in {2, 4, 30, 250},
        // k = 3, d = 1, 100,000 noise paths per n, each a fresh window of n N(0, 1) changes and an independent
        // N(0, 1) move; the fire count lies in the 99 % binomial interval (scipy binom.interval: ppf(0.005),
        // ppf(0.995)) of paths x the operation's own false_alarm_rate. A 6-sigma planted move fires on at least
        // 99.9 % of the n = 250 paths.
        Random rnd = new Random(20261119);
        int paths = 100_000;
        double k = 3.0;
        StringBuilder rec = new StringBuilder();
        boolean ok = true;
        for (int n : new int[] {2, 4, 30, 250}) {
            int fires = 0;
            int planted = 0;
            double[] z = new double[n];
            for (int p = 0; p < paths; p++) {
                for (int i = 0; i < n; i++) {
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
                if (p < 100) { // the operation itself agrees with the rule on a sample
                    assertEquals(fire, StageK.triggerCheck(z, 0.0, next, 1.0, k).fire());
                }
            }
            double[] window = new double[n];
            for (int i = 0; i < n; i++) {
                window[i] = i == n - 1 && n % 2 == 1 ? 0.5 : i % 2 == 0 ? 1.0 : -1.0;
            }
            double rate = StageK.triggerCheck(window, 0.0, 0.0, 1.0, k).falseAlarmRate();
            int lo = binomPpf(paths, rate, 0.005);
            int hi = binomPpf(paths, rate, 0.995);
            boolean passed = lo <= fires && fires <= hi;
            ok = ok && passed && (n != 250 || planted >= 0.999 * paths);
            rec.append(rec.length() == 0 ? "" : ", ").append('"').append(n).append("\": {\"fires\": ").append(fires)
                    .append(", \"false_alarm_rate\": ").append(rate).append(", \"nominal_rate\": ")
                    .append(2.0 * org.quantforge.core.Normal.cdf(-k)).append(", \"binomial_99_interval\": [")
                    .append(lo).append(", ").append(hi).append("], \"planted_6_sigma_fires\": ").append(planted)
                    .append(", \"pass\": ").append(passed).append('}');
        }
        evidence("trigger_simulation_kr232", "{\"paths\": " + paths + ", \"k\": " + k
                + ", \"seed\": \"java.util.Random(20261119)\", \"by_window\": {" + rec + "}, \"pass\": " + ok + "}");
        assertTrue(ok, rec.toString());
    }

    @Test
    void falseAlarmRateIsStudentTAndNominalRateTwiceTheNormalTail() {
        // KR-6 states 2 (1 - N(k)) = 2 N(-k) (nominal_rate); at k = 30 a bare erfc(k / sqrt 2) is 1.2e-13 off
        // (trig_k-0009, mpmath 50 digits).
        double[] c = {1, -1, 1, -1};
        assertEquals(2.0 * org.quantforge.core.Normal.cdf(-3.0), StageK.triggerCheck(c, 100, 105, 1, 3).nominalRate());
        double far = StageK.triggerCheck(c, 100, 105, 1, 30).nominalRate();
        assertTrue(Math.abs(far / 9.813427854296374e-198 - 1.0) <= 1e-14, () -> "rate " + far);
        // KR-232: P(|T_nu| > k), against the Python reference (stage_k.student_t_two_sided_tail); the even nu use
        // only + - * / and sqrt (same bits), the odd nu one atan2 (tail_probability class, 1e-11 relative).
        double[][] ref = {{1, 3.0, 0.20483276469913345}, {3, 3.0, 0.05766888562243732},
                {4, 0.5, 0.6433299631818632}, {29, 3.0, 0.0054991921339034135}, {249, 3.0, 0.0029737859324150294},
                {1, 1e-3, 0.999363380439839}, {2, 40.0, 0.0006244146721847407}, {7, 30.0, 1.1788468880733127e-08},
                {100000, 3.0, 0.0027004608840696964}};
        for (double[] r : ref) {
            double got = StageK.studentTTwoSidedTail((int) r[0], r[1]);
            if (((int) r[0]) % 2 == 0) {
                assertEquals(r[2], got, 0.0, () -> r[0] + " " + r[1]);
            } else {
                assertTrue(rel(got, r[2]) <= 1e-11, () -> r[0] + " " + r[1] + ": " + got);
            }
        }
        assertEquals(StageK.studentTTwoSidedTail(3, 3.0), StageK.triggerCheck(c, 100, 105, 1, 3).falseAlarmRate());
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
        code("E_LIMIT", () -> StageK.triggerCheck(big, 0, Double.NaN, 1, -1)); // KR-230: E_LIMIT first
        code("E_DOMAIN", () -> StageK.triggerCheck(new double[] {1.0}, 0, Double.NaN, 1, 3)); // finite, then shape
        code("E_INPUT", () -> StageK.triggerCheck(new double[] {1.0}, 0, 0, 1, -1)); // shape, then E_DOMAIN
        // KR-233: a constant window is E_DOMAIN whatever the rounding (sigma 1.7e-17 in binary64 here)
        code("E_DOMAIN", () -> StageK.triggerCheck(new double[] {0.1, 0.1, 0.1}, 0, 0, 1, 3));
        StageK.Trigger t = StageK.triggerCheck(c, 100, 104, 1, 3);
        assertTrue(t.fire());
        assertTrue(rel(t.nominalRate(), 0.002699796063260189) <= 1e-14);
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
        StringBuilder moves = new StringBuilder();
        double worst = 0;
        double minAbsH = 1;
        for (int m = 0; m < 1000; m++) {
            double h = -0.02 + 0.04 * rnd.nextDouble();
            StageK.Intraday r = StageK.deltaGammaBound(book, h);
            double full = StageK.zeroRevalue(book, h);
            double err = Math.abs(r.estimatePnl() - full);
            assertTrue(err <= r.bound(), h + ": " + err + " > " + r.bound());
            assertEquals(StageK.LABEL, r.label());
            worst = Math.max(worst, err / r.bound());
            minAbsH = Math.min(minAbsH, Math.abs(h));
            moves.append(m == 0 ? "" : ", ").append('[').append(h).append(", ").append(r.estimatePnl()).append(", ")
                    .append(full).append(", ").append(r.bound()).append(']');
        }
        StringBuilder bk = new StringBuilder();
        for (StageK.ZeroPosition p : book) {
            bk.append(bk.length() == 0 ? "" : ", ").append('[').append(p.notional()).append(", ").append(p.maturity())
                    .append(", ").append(p.yield()).append(']');
        }
        evidence("intraday_bound_1000_moves", "{\"book\": [" + bk + "], \"seed\": \"java.util.Random(20261118)\""
                + ", \"columns\": [\"h\", \"estimate_pnl\", \"full_revaluation\", \"bound\"], \"moves\": [" + moves
                + "], \"violations\": 0, \"worst_error_over_bound\": " + worst + ", \"min_abs_h\": " + minAbsH + "}");
    }

    private static final double[] SWEEP_T = {1e-6, 1e-3, 0.25, 1.0, 5.0, 30.0, 100.0};
    private static final double[] SWEEP_Y = {-1.0, -0.01, 0.0, 0.04, 0.3, 1.0};
    private static final double[] SWEEP_N = {0.0, 1e-6, 1.0, 1e6, -1e6, 1e15, -1e15};

    private static double[] sweepH() {
        List<Double> h = new ArrayList<>();
        h.add(0.0);
        for (int e : new int[] {30, 25, 20, 16, 14, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1}) {
            double m = Math.pow(10.0, -e); // the moves of the Python sweep (x * 10.0**-e)
            h.add(m);
            h.add(-m);
        }
        for (double x : new double[] {0.5, -0.5, 1.0, -1.0, 1.0 / 3.0, -0.07}) {
            h.add(x);
        }
        return h.stream().mapToDouble(Double::doubleValue).toArray();
    }

    /**
     * KR-234 acceptance, binary64 half (as Python test_intraday_bound_small_move_sweep): |estimate - V_64| <= bound on
     * every book of the sweep at every move, V_64 the binary64 revaluation. Books: every single position of the
     * grid, hedged books, delta-neutral pairs and 300 seeded random books (java.util.Random(20261119), not the
     * Python stream).
     */
    @Test
    void intradayBoundSmallMoveSweep() {
        List<List<StageK.ZeroPosition>> books = new ArrayList<>();
        for (double n : SWEEP_N) {
            for (double t : SWEEP_T) {
                for (double y : SWEEP_Y) {
                    books.add(List.of(new StageK.ZeroPosition(n, t, y)));
                }
            }
        }
        for (double t : SWEEP_T) {
            for (double y : SWEEP_Y) {
                books.add(List.of(new StageK.ZeroPosition(1e6, t, y),
                        new StageK.ZeroPosition(-1e6 * (1 + 1e-12), t, y)));
                books.add(List.of(new StageK.ZeroPosition(1e6, t, y), new StageK.ZeroPosition(-1e6, t, y)));
                if (2 * t <= 100) {
                    double n2 = -1e6 * t * Math.exp(-y * t) / (2 * t * Math.exp(-y * 2 * t));
                    books.add(List.of(new StageK.ZeroPosition(1e6, t, y), new StageK.ZeroPosition(n2, 2 * t, y)));
                }
            }
        }
        Random rnd = new Random(20261119);
        for (int b = 0; b < 300; b++) {
            int size = 1 + rnd.nextInt(20);
            List<StageK.ZeroPosition> book = new ArrayList<>();
            for (int i = 0; i < size; i++) {
                book.add(new StageK.ZeroPosition(-1e9 + 2e9 * rnd.nextDouble(),
                        SWEEP_T[rnd.nextInt(SWEEP_T.length)] * (0.5 + 0.5 * rnd.nextDouble()),
                        -0.05 + 0.15 * rnd.nextDouble()));
            }
            books.add(book);
        }
        double worst = 0;
        int cases = 0;
        double[] moves = sweepH();
        for (List<StageK.ZeroPosition> book : books) {
            for (double h : moves) {
                StageK.Intraday r = StageK.deltaGammaBound(book, h);
                double gap = Math.abs(r.estimatePnl() - StageK.zeroRevalue(book, h));
                assertTrue(gap <= r.bound(), () -> book + " h=" + h + ": " + gap + " > " + r.bound());
                if (r.bound() != 0) {
                    worst = Math.max(worst, gap / r.bound());
                }
                cases++;
            }
        }
        evidence("intraday_bound_sweep_kr234", "{\"cases\": " + cases + ", \"worst_binary64_gap_over_bound\": "
                + worst + "}");
        assertTrue(cases > 20_000, "cases " + cases);
        // KA-A6 at h = 1e-9 (Python reference value of the bound; the old output pair failed by a factor 21.6)
        StageK.Intraday one = StageK.deltaGammaBound(List.of(new StageK.ZeroPosition(1e6, 5.0, 0.04)), 1e-9);
        assertTrue(rel(one.bound(), 1.7469352659511083e-17) <= 1e-12, () -> "bound " + one.bound());
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
        code("E_LIMIT", () -> StageK.deltaGammaBound(big, 0.01)); // KR-230: before E_DOMAIN
        code("E_DOMAIN", () -> StageK.deltaGammaBound(List.of(), Double.NaN)); // finite rule, then shape
        StageK.Intraday z = StageK.deltaGammaBound(List.of(p), 0.0);
        assertEquals(0.0, z.estimatePnl());
        assertEquals(0.0, z.bound());
    }

    // --- Richardson ----------------------------------------------------------------------------------

    @Test
    void richardsonPaths() {
        code("E_INPUT", () -> StageK.richardsonCheck(new double[] {1.0}, 2, 2));
        code("E_DOMAIN", () -> StageK.richardsonCheck(new double[] {1.0}, Double.NaN, 2)); // KR-230
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
