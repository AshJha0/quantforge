package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.DoubleUnaryOperator;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.quantforge.core.Json;
import org.quantforge.risk.StageK;

/**
 * K-8 {@code CN_RANNACHER_SMOOTHED} (KR-8, PROPOSED): the Python build's values on a small grid, the tangent ladder
 * against its own bumps (acceptance 5), the cell-average smoothing, and acceptance 3 (201/401/801), which runs only
 * with {@code QF_K8_ACCEPTANCE=1}; the Python result is {@code oracle/K8_ACCEPTANCE_W1.json} (a known miss).
 */
class BermudanK8Test {
    private static final Path ROOT = Path.of("..");

    private record Case(double[] times, double[] dfs, double a, double sigma, double[] pay, double rate,
            boolean payer, double notional, double[] exercise, double width) {}

    private static double[] reals(Object o) {
        List<?> l = (List<?>) o;
        double[] out = new double[l.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = ((Json.Number) l.get(i)).value();
        }
        return out;
    }

    private static double num(Map<?, ?> m, String k) {
        return ((Json.Number) m.get(k)).value();
    }

    private static Case ladderCase(int index) throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(ROOT.resolve(
                "datasets/golden/stage_g/aadladder_g.json"))).value();
        Map<?, ?> i = (Map<?, ?>) ((Map<?, ?>) ((List<?>) doc.get("cases")).get(index)).get("inputs");
        Map<?, ?> c = (Map<?, ?>) i.get("curve");
        return new Case(reals(c.get("times")), reals(c.get("discount_factors")), num(i, "mean_reversion"),
                num(i, "sigma"), reals(i.get("payment_times")), num(i, "fixed_rate"),
                "PAYER".equals(i.get("swaption_type")), num(i, "notional"), reals(i.get("exercise_times")),
                num((Map<?, ?>) i.get("grid"), "width"));
    }

    private static BermudanLadder.Ladder ladder(Case c, int nx, int spy) {
        return BermudanK8.ladder(c.times(), c.dfs(), c.a(), c.sigma(), c.pay(), c.rate(), c.payer(), c.notional(),
                c.exercise(), new ShortRateFd.Grid(nx, spy, c.width()));
    }

    private static double price(Case c, double[] dfs, double a, double s, int nx, int spy) {
        return BermudanK8.price(c.times(), dfs, a, s, c.pay(), c.rate(), c.payer(), c.notional(), c.exercise(),
                new ShortRateFd.Grid(nx, spy, c.width()));
    }

    private static double[] row(BermudanLadder.Ladder l) {
        int n = l.dDiscountFactors().length;
        double[] r = new double[n + 3];
        r[0] = l.price();
        System.arraycopy(l.dDiscountFactors(), 0, r, 1, n);
        r[n + 1] = l.dMeanReversion();
        r[n + 2] = l.dSigma();
        return r;
    }

    /** Python bermudan_k8.bermudan_ladder on aadladder_g-0001 and -0002 inputs, grid 41/20 (2026-11-19). */
    private static final double[][] PYTHON_41_20 = {
        {23242.10538303547, -2239.614460578422, 211874.58626052644, 167312.8801939704, 135668.58189923508,
            -231817.56140334287, -346529.0802496462, 0.0, 0.0, 0.0, 0.0, -56055.23884443008, 2319343.9308582232},
        {15132.751343821015, -1458.2195175014667, 99287.02462202832, 133644.6647674322, 145269.93540935125,
            -145945.81731299608, -278764.61920365266, 0.0, 0.0, 0.0, 0.0, -55104.22854697141, 2187522.535242841},
    };

    @Test
    void matchesPythonOnSmallGrid() throws IOException {
        for (int k = 0; k < 2; k++) {
            double[] got = row(ladder(ladderCase(k), 41, 20));
            double scale = 0;
            for (double x : PYTHON_41_20[k]) {
                scale = Math.max(scale, Math.abs(x));
            }
            for (int j = 0; j < got.length; j++) {
                assertTrue(Math.abs(got[j] - PYTHON_41_20[k][j]) <= 1e-10 * scale,
                        k + "/" + j + ": " + got[j] + " vs " + PYTHON_41_20[k][j]);
            }
            Case c = ladderCase(k);
            assertEquals(got[0], price(c, c.dfs(), c.a(), c.sigma(), 41, 20), 1e-9 * Math.abs(got[0]));
        }
    }

    private static double bump(DoubleUnaryOperator f, double x, double h) {
        double d1 = (f.applyAsDouble(x + h) - f.applyAsDouble(x - h)) / (2 * h);
        double d2 = (f.applyAsDouble(x + h / 2) - f.applyAsDouble(x - h / 2)) / h;
        return (4 * d2 - d1) / 3;
    }

    /** Acceptance 5 on a small grid: the ladder equals a Richardson-extrapolated central bump of the same scheme. */
    @Test
    void ladderEqualsItsOwnBumps() throws IOException {
        Case c = ladderCase(1);
        int nx = 41;
        int spy = 20;
        BermudanLadder.Ladder l = ladder(c, nx, spy);
        double scale = 0;
        for (double x : l.dDiscountFactors()) {
            scale = Math.max(scale, Math.abs(x));
        }
        for (int j = 0; j < c.dfs().length; j++) {
            final int jj = j;
            double got = bump(x -> {
                double[] d = c.dfs().clone();
                d[jj] = x;
                return price(c, d, c.a(), c.sigma(), nx, spy);
            }, c.dfs()[j], 1e-4 * c.dfs()[j]);
            assertTrue(Math.abs(got - l.dDiscountFactors()[j]) <= 1e-8 * scale, j + ": " + got);
        }
        double ga = bump(x -> price(c, c.dfs(), x, c.sigma(), nx, spy), c.a(), 1e-3 * c.a());
        assertTrue(Math.abs(ga - l.dMeanReversion()) <= 1e-8 * Math.abs(ga), "a: " + ga);
        double gs = bump(x -> price(c, c.dfs(), c.a(), x, nx, spy), c.sigma(), 1e-3 * c.sigma());
        assertTrue(Math.abs(gs - l.dSigma()) <= 1e-8 * Math.abs(gs), "sigma: " + gs);
    }

    @Test
    void smoothingIsACellAverage() {
        double[][] v = {{0.0}, {0.0}, {0.0}};
        double[][] e = {{-1.0}, {0.0}, {1.0}};
        double[][] got = BermudanK8.smoothedMax(v, e);
        // node 1: cell [-0.5, 0.5] of max(x, 0) = mean 1/8; node 2: [0.5, 1.5] = 1; node 0: 0
        assertArrayEquals(new double[] {0.0, 0.125, 1.0}, new double[] {got[0][0], got[1][0], got[2][0]});
        double[][] w = BermudanK8.smoothedMax(new double[][] {{0.0}, {0.0}, {0.0}}, new double[][] {{1}, {0}, {-1}});
        assertArrayEquals(new double[] {1.0, 0.125, 0.0}, new double[] {w[0][0], w[1][0], w[2][0]});
    }

    @Test
    void dualArithmetic() {
        double[] u = {2, 1, 0};
        double[] v = {4, 0, 1};
        assertArrayEquals(new double[] {8, 4, 2}, BermudanK8.mul(u, v));
        assertArrayEquals(new double[] {0.5, 0.25, -0.125}, BermudanK8.div(u, v));
        assertArrayEquals(new double[] {6, 1, 1}, BermudanK8.add(u, v));
        assertArrayEquals(new double[] {-2, 1, -1}, BermudanK8.sub(u, v));
        assertArrayEquals(new double[] {4, 2, 0}, BermudanK8.scale(2, u));
    }

    /**
     * Acceptance 3: on 201/401/801, {@code num.richardson.check} with assumed order 2 gives OK and an observed order in
     * [1.5, 2.5] on the price and every ladder entry that is not a structural zero. Known miss in Python (18 entries);
     * this test records the Java result and is not tuned.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "QF_K8_ACCEPTANCE", matches = "1")
    void acceptance3ObservedOrder() throws IOException {
        Map<?, ?> record = (Map<?, ?>) Json.parse(Files.readString(ROOT.resolve("oracle/K8_ACCEPTANCE_W1.json")))
                .value();
        Map<?, ?> pyValues = (Map<?, ?>) record.get("values");
        List<String> bad = new ArrayList<>();
        Map<String, Object> values = new LinkedHashMap<>();
        double worstGap = 0;
        for (int index = 0; index < 3; index++) {
            Case c = ladderCase(index);
            List<double[]> rows = new ArrayList<>();
            int[][] grids = {{201, 100}, {401, 200}, {801, 400}};
            List<?> py = (List<?>) pyValues.get("aadladder_g-000" + (index + 1));
            for (int g = 0; g < 3; g++) {
                double[] r = row(ladder(c, grids[g][0], grids[g][1]));
                rows.add(r);
                double[] p = reals(py.get(g));
                double scale = 0;
                for (double x : p) {
                    scale = Math.max(scale, Math.abs(x));
                }
                for (int k = 0; k < r.length; k++) {
                    worstGap = Math.max(worstGap, Math.abs(r[k] - p[k]) / scale);
                }
            }
            values.put("aadladder_g-000" + (index + 1), rows);
            for (int k = 0; k < rows.get(0).length; k++) {
                double[] vals = {rows.get(0)[k], rows.get(1)[k], rows.get(2)[k]};
                if (vals[0] == 0.0 && vals[1] == 0.0 && vals[2] == 0.0) {
                    continue;
                }
                StageK.Richardson rc = StageK.richardsonCheck(vals, 2.0, 2.0);
                Double obs = rc.observedOrder();
                if (!rc.status().equals("OK") || obs == null || obs < 1.5 || obs > 2.5) {
                    bad.add("[" + index + ", " + k + ", \"" + rc.status() + "\", " + obs + "]");
                }
            }
        }
        StringBuilder b = new StringBuilder();
        Json.write(b, Map.of("build", "java25 (org.quantforge.pricing.BermudanK8, tangent-mode ladder)",
                "failures_count", bad.size(), "max_gap_vs_python_relative_to_row_scale", worstGap));
        System.out.println("K-8 acceptance 3 (Java): " + b + " failures=" + bad);
        List<?> pyFailures = (List<?>) record.get("failures");
        assertEquals(pyFailures.size(), bad.size(), "Java failures differ in number from Python's: " + bad);
        assertTrue(worstGap <= 1e-9, "Java differs from the Python record by " + worstGap);
        assertTrue(bad.isEmpty(), "K-8 acceptance 3 fails on " + bad.size() + " entries (KR-8, K-QB)");
    }
}
