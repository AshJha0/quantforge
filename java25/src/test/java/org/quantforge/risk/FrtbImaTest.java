package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.quantforge.risk.FrtbDrcTest.code;
import static org.quantforge.risk.FrtbDrcTest.d;
import static org.quantforge.risk.FrtbDrcTest.table;

import java.io.IOException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;

/**
 * FRTB IMA (K-8f): the shared tables (KR-50), unit rules mirroring python/tests/test_stage_k_w2a.py, and the spec's
 * A3 properties. The SciPy cross-checks of the Python suite are replaced by definitional checks (a brute-force
 * Spearman on average ranks and a brute-force KS over the pooled values), since the Java build has no SciPy.
 */
class FrtbImaTest {
    @Test
    void parametersMatchTables() throws IOException {
        Map<String, Object> f = table("mar31_rfet");
        assertEquals(d(f.get("rfet.min_obs_per_year")), FrtbImaTables.RFET_MIN_DAYS);
        assertEquals(d(f.get("rfet.window_days")), FrtbImaTables.RFET_WINDOW_DAYS);
        assertEquals(d(f.get("rfet.min_obs_per_window")), FrtbImaTables.RFET_MIN_PER_WINDOW);
        assertEquals(d(f.get("rfet.alt_min_obs_12m")), FrtbImaTables.RFET_ALT_MIN_DAYS);
        assertEquals(d(f.get("rfet.lookback_months")), FrtbImaTables.RFET_LOOKBACK_MONTHS);
        Map<String, double[]> rows = Map.of("A", FrtbImaTables.RFET_A, "B", FrtbImaTables.RFET_B, "C",
                FrtbImaTables.RFET_C, "D", FrtbImaTables.RFET_D);
        for (Map.Entry<String, double[]> e : rows.entrySet()) {
            List<?> printed = (List<?>) f.get("bucket." + e.getKey());
            for (int k = 0; k < printed.size(); k++) {
                List<?> pair = (List<?>) printed.get(k);
                assertEquals(d(pair.get(0)), e.getValue()[k]);
                if (k + 1 < printed.size()) {
                    assertEquals(d(pair.get(1)), e.getValue()[k + 1]);
                } else {
                    assertEquals(e.getKey().equals("D") ? "1.00" : "inf", pair.get(1));
                }
            }
        }
        assertEquals(1.0, FrtbImaTables.RFET_D_UPPER);
        Map<String, Object> p = table("mar32_pla");
        Map<?, ?> mult = (Map<?, ?>) p.get("backtest.zone_multiplier");
        for (int k = 0; k < 10; k++) {
            assertEquals(d(mult.get(Integer.toString(k))), FrtbImaTables.MULTIPLIER[k]);
        }
        assertEquals(d(mult.get("10+")), FrtbImaTables.MULTIPLIER_RED);
        assertEquals(d(p.get("pla.green.spearman_above")), FrtbImaTables.PLA_GREEN_SPEARMAN);
        assertEquals(d(p.get("pla.red.spearman_below")), FrtbImaTables.PLA_RED_SPEARMAN);
        assertEquals(d(p.get("pla.green.ks_below")), FrtbImaTables.PLA_GREEN_KS_PERCENT / 100.0);
        assertEquals(d(p.get("pla.red.ks_above")), FrtbImaTables.PLA_RED_KS_PERCENT / 100.0);
        assertEquals(d(p.get("pla.window_days")), FrtbImaTables.PLA_WINDOW);
        Map<String, Object> m = table("mar33_ima");
        Map<?, ?> lhj = (Map<?, ?>) m.get("lh.j");
        for (int j = 1; j <= 5; j++) {
            assertEquals(d(lhj.get(Integer.toString(j))), FrtbImaTables.LIQUIDITY_HORIZONS[j - 1]);
        }
        assertEquals(d(m.get("es.confidence")), FrtbImaTables.ES_CONFIDENCE);
        assertEquals(d(m.get("es.base_horizon_days")), FrtbImaTables.BASE_HORIZON);
        Map<?, ?> lh = (Map<?, ?>) m.get("lh.table");
        assertEquals(new ArrayList<>(lh.keySet()), FrtbIma.LH_CATEGORIES);
        for (int k = 0; k < FrtbImaTables.LH_CATEGORY.length; k++) {
            assertEquals(d(lh.get(FrtbImaTables.LH_CATEGORY[k])), FrtbImaTables.LH_DAYS[k]);
        }
        assertEquals(m.get("lh.specified_fx_pairs"), List.of(FrtbImaTables.SPECIFIED_FX_PAIRS));
        assertEquals(d(m.get("imcc.rho")), FrtbImaTables.IMCC_RHO);
        assertEquals(d(m.get("ses.rho")), FrtbImaTables.SES_RHO);
        assertEquals(FrtbIma.NORMAL_ES_FACTOR_DOC, FrtbIma.normalEsFactor(), 1e-15); // one ulp apart
    }

    // ---- PLA -----------------------------------------------------------------------------------------------

    @Test
    void plaAndPvalueDetails() {
        FrtbIma.Pla out = FrtbIma.pla(new double[] {1, 2, 3, 4}, new double[] {1, 2, 3, 4});
        assertEquals("GREEN", out.zone());
        assertEquals(1.0, out.spearman());
        assertEquals(1.0, out.ksPvalueAsymptotic());
        assertFalse(out.regulatoryWindow());
        assertEquals(-1.0, FrtbIma.pla(new double[] {1, 2, 3}, new double[] {3, 2, 1}).spearman());
        assertArrayEquals(new long[] {6, 2, 6, 6}, FrtbIma.doubledRanks(new double[] {5, 1, 5, 5}));
        assertArrayEquals(new long[] {3, 3, 6}, FrtbIma.doubledRanks(new double[] {-0.0, 0.0, 1})); // -0 ties +0
        assertEquals(1.0, FrtbIma.kolmogorovQ(0));
        assertEquals(1.0, FrtbIma.kolmogorovQ(0.01));
        assertEquals(0.0, FrtbIma.kolmogorovQ(40));
        assertEquals(1.0, FrtbIma.plaKsPvalue(0, 250));
        assertEquals("E_LIMIT", code(() -> FrtbIma.pla(new double[FrtbIma.MAX_PNL + 1], new double[1])));
        assertEquals("E_LIMIT", code(() -> FrtbIma.pla(new double[1], new double[FrtbIma.MAX_PNL + 1])));
        assertEquals("E_DOMAIN", code(() -> FrtbIma.pla(new double[] {1, 2, 3}, new double[] {1, 1, 1})));
        assertEquals("E_DOMAIN", code(() -> FrtbIma.pla(new double[] {1, 1, 1}, new double[] {1, 2, 3})));
        // zone boundaries are amber (KR-56): d = 9 at n = 100 is KS 0.09 exactly, not below
        double[] h = new double[100];
        double[] r = new double[100];
        for (int k = 0; k < 100; k++) {
            h[k] = k;
            r[k] = k < 91 ? k + 9 : k + 9.5;
        }
        FrtbIma.Pla edge = FrtbIma.pla(h, r);
        assertEquals(9, edge.ksCount());
        assertEquals("AMBER", edge.zone());
    }

    /** MAR32.42 printed p-values 0.264 and 0.055 (pla_k-0007, 0008: within 1e-3, fixed in the spec). */
    @Test
    void printedPvalues() {
        assertEquals(0.264, FrtbIma.plaKsPvalue(0.09, 250), 1e-3);
        assertEquals(0.055, FrtbIma.plaKsPvalue(0.12, 250), 1e-3);
    }

    /**
     * The two series of Q_KS agree where both converge (KR-117: either form alone stays within the tolerance for
     * x &gt; 0); here the theta form is evaluated at x &gt;= 1 and the alternating form at x &lt; 1.
     */
    @Test
    void kolmogorovSeriesAgree() {
        for (double x = 0.3; x < 4; x += 0.1) {
            double alt = 0;
            for (int k = 1; k < 200; k++) {
                alt += (k % 2 == 1 ? 2 : -2) * Math.exp(-2.0 * k * k * x * x);
            }
            double theta = 0;
            for (int k = 1; k < 200; k++) {
                theta += Math.exp(-(2.0 * k - 1) * (2.0 * k - 1) * Math.PI * Math.PI / (8 * x * x));
            }
            theta = 1 - Math.sqrt(2 * Math.PI) / x * theta;
            double q = FrtbIma.kolmogorovQ(x);
            assertEquals(alt, q, 1e-12 * Math.abs(alt) + 1e-15, "x " + x);
            assertEquals(theta, q, 1e-12 * Math.abs(q) + 1e-15, "x " + x);
        }
    }

    /** Spearman by definition: Pearson correlation of average ranks in doubles (MAR32.38, KR-56). */
    private static double spearmanByDefinition(double[] x, double[] y) {
        int n = x.length;
        double[] rx = new double[n];
        double[] ry = new double[n];
        for (int i = 0; i < n; i++) {
            int lessX = 0;
            int eqX = 0;
            int lessY = 0;
            int eqY = 0;
            for (int j = 0; j < n; j++) {
                lessX += x[j] < x[i] ? 1 : 0;
                eqX += x[j] == x[i] ? 1 : 0;
                lessY += y[j] < y[i] ? 1 : 0;
                eqY += y[j] == y[i] ? 1 : 0;
            }
            rx[i] = lessX + (eqX + 1) / 2.0;
            ry[i] = lessY + (eqY + 1) / 2.0;
        }
        double mx = (n + 1) / 2.0;
        double sxy = 0;
        double sxx = 0;
        double syy = 0;
        for (int i = 0; i < n; i++) {
            sxy += (rx[i] - mx) * (ry[i] - mx);
            sxx += (rx[i] - mx) * (rx[i] - mx);
            syy += (ry[i] - mx) * (ry[i] - mx);
        }
        return sxy / Math.sqrt(sxx * syy);
    }

    /** KS count by definition: max over pooled values of |#{y &lt;= v} - #{x &lt;= v}| (MAR32.39-32.41). */
    private static long ksByDefinition(double[] x, double[] y) {
        long best = 0;
        for (double[] side : new double[][] {x, y}) {
            for (double v : side) {
                long cx = 0;
                long cy = 0;
                for (double a : x) {
                    cx += a <= v ? 1 : 0;
                }
                for (double b : y) {
                    cy += b <= v ? 1 : 0;
                }
                best = Math.max(best, Math.abs(cy - cx));
            }
        }
        return best;
    }

    private static double g(double x) {
        return Math.exp(x / 10) + 3 * x;
    }

    @Property(tries = 300)
    void plaInvariancesAndDefinitions(@ForAll long seed) {
        Random rnd = new Random(seed);
        int n = 3 + rnd.nextInt(38);
        double[] h = new double[n];
        double[] r = new double[n];
        Set<Double> hs = new HashSet<>();
        Set<Double> rs = new HashSet<>();
        for (int k = 0; k < n; k++) {
            h[k] = rnd.nextInt(101) - 50;
            r[k] = rnd.nextInt(101) - 50;
            hs.add(h[k]);
            rs.add(r[k]);
        }
        if (hs.size() < 2 || rs.size() < 2) {
            return;
        }
        FrtbIma.Pla base = FrtbIma.pla(h, r);
        FrtbIma.Pla swapped = FrtbIma.pla(r, h);
        assertEquals(base.spearman(), swapped.spearman(), 1e-15);
        assertEquals(base.ksCount(), swapped.ksCount());
        double[] gh = new double[n];
        double[] gr = new double[n];
        double[] cube = new double[n];
        for (int k = 0; k < n; k++) {
            gh[k] = g(h[k]);
            gr[k] = g(r[k]);
            cube[k] = r[k] * r[k] * r[k];
        }
        // strictly increasing transforms: spearman invariant for either series, KS for a common one
        assertEquals(base.spearman(), FrtbIma.spearman(gh, r), 1e-15);
        assertEquals(base.spearman(), FrtbIma.spearman(h, cube), 1e-15);
        assertEquals(base.ksCount(), FrtbIma.ksCount(gh, gr));
        // the definitions, computed the slow way
        assertEquals(spearmanByDefinition(h, r), base.spearman(), 1e-12);
        assertEquals(ksByDefinition(h, r), base.ksCount());
        assertEquals((double) base.ksCount() / n, base.ks());
    }

    // ---- liquidity horizons --------------------------------------------------------------------------------

    @Test
    void liquidityHorizonDetails() {
        assertTrue(FrtbIma.fxPairSpecified("CHF/JPY")); // cross through USD
        assertTrue(FrtbIma.fxPairSpecified("JPY/USD")); // order ignored
        assertFalse(FrtbIma.fxPairSpecified("ISK/PLN"));
        assertFalse(FrtbIma.fxPairSpecified("USD"));
        assertEquals(20, FrtbIma.liquidityHorizon(null, "ISK/PLN", null, null).n());
        assertEquals("table", FrtbIma.liquidityHorizon("EQ_large_cap", null, null, 200.0).rule());
        assertEquals("index+maturity", FrtbIma.liquidityHorizon(null, null,
                List.of(new FrtbIma.Constituent(1.0, 120)), 1.0).rule());
        assertEquals(120, FrtbIma.nextHorizon(500));
        assertEquals("E_LIMIT", code(() -> FrtbIma.liquidityHorizon(null, null,
                Collections.nCopies(FrtbIma.MAX_LIST + 1, new FrtbIma.Constituent(0, 10)), null)));
        assertEquals("E_INPUT", code(() -> FrtbIma.liquidityHorizon(null, null, null, null)));
    }

    // ---- ES, stressed ES, IMCC, SES, capital ---------------------------------------------------------------

    @Test
    void esAndCapitalDetails() {
        assertArrayEquals(new double[] {1, 1, 2, 2, 6}, FrtbIma.horizonWeights());
        double[] e = {};
        FrtbIma.EsLh out = FrtbIma.esLh(null, null, new double[][] {{-1, -2, -3}, e, e, e, e});
        assertEquals("pnl", out.mode());
        assertEquals(3.0, out.es());
        assertEquals("E_LIMIT", code(() -> FrtbIma.esLh(null, null,
                new double[][] {new double[FrtbIma.MAX_PNL + 1], e, e, e, e})));
        Map<String, double[]> classes = new LinkedHashMap<>();
        classes.put("CS", new double[] {1, 1, 2});
        classes.put("IR", new double[] {1, 2, 1});
        FrtbIma.Imcc im = FrtbIma.imcc(new double[] {1, 1, 1}, classes);
        assertEquals(List.of("CS"), im.classesFloored());
        assertEquals(List.of("IR", "CS"), new ArrayList<>(im.classes().keySet())); // KR-114 order
        FrtbIma.Capital c = FrtbIma.capital(10, 0, 10, 0, 12, 0, List.of(), 0, 100, 0.25);
        assertEquals(2.25, c.mC());
        assertEquals(0, c.k());
        assertEquals(45.0, c.acrTotal()); // no desks: SA_G,A 0 (KR-120)
        assertEquals("E_LIMIT", code(() -> FrtbIma.capital(1, 1, 1, 1, 0, 0,
                Collections.nCopies(FrtbIma.MAX_LIST + 1, new FrtbIma.Desk("GREEN", 1)), 0, 1, 0)));
        assertEquals("E_LIMIT", code(() -> FrtbIma.ses(new double[FrtbIma.MAX_LIST + 1], e, e)));
        // worked example cap_k-0002 (frtb-ima.md)
        c = FrtbIma.capital(100, 20, 90, 15, 6, 30, List.of(new FrtbIma.Desk("GREEN", 150),
                new FrtbIma.Desk("AMBER", 100)), 40, 300, 0);
        assertEquals(252.72, c.acrTotal(), 1e-12);
        assertEquals(0.2, c.k(), 1e-15);
    }

    @Property(tries = 200)
    void esCascadeScaling(@ForAll long seed) {
        Random rnd = new Random(seed);
        int j = rnd.nextInt(5);
        double e = rnd.nextDouble() * 1e6;
        double[] w = FrtbIma.horizonWeights();
        double[] single = new double[5];
        single[j] = e;
        assertEquals(e * Math.sqrt(w[j]), FrtbIma.esLh(single, null, null).es(), 1e-14 * e);
        // every risk factor at horizon LH_j: ES_1 = ... = ES_j = E, the rest 0 -> E sqrt(LH_j / 10) (KR-122)
        double[] nested = new double[5];
        for (int k = 0; k <= j; k++) {
            nested[k] = e;
        }
        double lh = FrtbImaTables.LIQUIDITY_HORIZONS[j];
        assertEquals(e * Math.sqrt(lh / 10), FrtbIma.esLh(nested, null, null).es(), 1e-14 * e);
    }

    @Property(tries = 200)
    void esStressedFloor(@ForAll long seed) {
        Random rnd = new Random(seed);
        double rs = rnd.nextDouble() * 1e6;
        double fc = rnd.nextDouble() * 1e6;
        double rc = 1e-6 + rnd.nextDouble() * 1e6;
        assertTrue(FrtbIma.esStressed(rs, fc, rc).es() >= rs);
    }

    private static double[] charges(Random rnd) {
        double[] v = new double[rnd.nextInt(21)];
        for (int k = 0; k < v.length; k++) {
            v[k] = rnd.nextDouble() * 1e6;
        }
        return v;
    }

    private static double sum(double[] v) {
        double s = 0;
        for (double x : v) {
            s += x;
        }
        return s;
    }

    @Property(tries = 200)
    void sesBounds(@ForAll long seed) {
        Random rnd = new Random(seed);
        double[] a = charges(rnd);
        double[] b = charges(rnd);
        double[] c = charges(rnd);
        FrtbIma.Ses out = FrtbIma.ses(a, b, c);
        double ss = 0;
        for (double x : c) {
            ss += x * x;
        }
        double rss = Math.sqrt(ss);
        double total = sum(c);
        assertTrue(rss * (1 - 1e-12) - 1e-9 <= out.other() && out.other() <= total * (1 + 1e-12) + 1e-9);
        assertTrue(out.ses() <= sum(a) + sum(b) + total + 1e-6);
        // a single entry in any list equals that entry (from 1e-100: smaller squares underflow)
        double x = rnd.nextBoolean() ? 0.0 : Math.pow(10, -100 + 200 * rnd.nextDouble());
        double[][] lists = {{}, {}, {}};
        lists[rnd.nextInt(3)] = new double[] {x};
        assertEquals(x, FrtbIma.ses(lists[0], lists[1], lists[2]).ses(), 1e-15 * x);
    }

    // ---- RFET ----------------------------------------------------------------------------------------------

    @Test
    void rfetDetails() {
        assertEquals(LocalDate.of(2023, 2, 28), FrtbIma.monthsBack(LocalDate.of(2024, 2, 29), 12));
        assertEquals(LocalDate.of(2026, 2, 28), FrtbIma.monthsBack(LocalDate.of(2026, 3, 31), 1));
        assertEquals(LocalDate.of(2025, 1, 15), FrtbIma.monthsBack(LocalDate.of(2026, 1, 15), 12));
        List<LocalDate> every = new ArrayList<>();
        for (int k = 0; k < 365; k++) {
            every.add(LocalDate.of(2025, 7, 1).plusDays(k));
        }
        every.add(LocalDate.of(2026, 7, 1));
        every.add(LocalDate.of(2020, 1, 1));
        FrtbIma.Rfet out = FrtbIma.rfet(LocalDate.of(2026, 6, 30), every);
        assertEquals(365, out.distinctDays());
        assertNull(out.firstFailingWindowStart());
        assertTrue(out.pass());
        assertEquals(90L, out.minWindowCount());
        assertEquals("E_LIMIT", code(() -> FrtbIma.rfet(LocalDate.of(2026, 6, 30),
                Collections.nCopies(FrtbIma.MAX_LIST + 1, LocalDate.of(2026, 1, 1)))));
        assertNull(FrtbIma.rfetBucket("A", 40.0, null).upper());
        assertEquals(1.0, FrtbIma.rfetBucket("D", null, 0.99).upper());
        assertEquals(1, FrtbIma.rfetBucket("A", 0.0, null).bucket());
        assertEquals(1, FrtbIma.rfetBucket("B", -0.0, null).bucket());
        assertEquals(2, FrtbIma.rfetBucket("C", 1.5, null).bucket());
        assertEquals(3.5, FrtbIma.rfetBucket("C", 1.5, null).upper());
        assertEquals("E_INPUT", code(() -> FrtbIma.rfetBucket("A", null, null)));
    }

    @Property(tries = 100)
    void rfetCountingWindows(@ForAll long seed) {
        Random rnd = new Random(seed);
        LocalDate asOf = LocalDate.of(2026, 6, 30);
        List<LocalDate> obs = new ArrayList<>();
        int size = rnd.nextInt(61);
        for (int k = 0; k < size; k++) {
            obs.add(asOf.minusDays(rnd.nextInt(431) - 30));
        }
        FrtbIma.Rfet out = FrtbIma.rfet(asOf, obs);
        LocalDate start = LocalDate.of(2025, 7, 1);
        Set<LocalDate> inside = new HashSet<>();
        for (LocalDate d : obs) {
            if (!d.isBefore(start) && !d.isAfter(asOf)) {
                inside.add(d);
            }
        }
        assertEquals(inside.size(), out.distinctDays());
        List<LocalDate> twice = new ArrayList<>(obs);
        twice.addAll(obs);
        assertEquals(out, FrtbIma.rfet(asOf, twice)); // duplicates count once
        long min = Long.MAX_VALUE;
        for (LocalDate s = start; !s.plusDays(89).isAfter(asOf); s = s.plusDays(1)) {
            long count = 0;
            for (LocalDate d : inside) {
                count += !d.isBefore(s) && !d.isAfter(s.plusDays(89)) ? 1 : 0;
            }
            min = Math.min(min, count);
        }
        assertEquals(min, (long) out.minWindowCount());
        assertEquals(inside.size() >= 24 && min >= 4, out.crit1());
        assertEquals(inside.size() >= 100, out.crit2());
    }

    @Test
    void jsonNumbersParse() {
        assertEquals(2.0, d(new Json.Number(2, "2")));
    }
}
