package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.DoubleUnaryOperator;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.quantforge.core.Json;
import org.quantforge.risk.StageK;

/**
 * K-8 {@code CN_RANNACHER_SMOOTHED} (KR-8 as revised by KR-18): the Python build's values on a small grid, the tangent
 * ladder against its own bumps (acceptance 5), the smoothing of spec step 5, exact zeros, time order, and acceptance 3
 * (201/401/801), which runs only with {@code QF_K8_ACCEPTANCE=1} against {@code oracle/K8_ACCEPTANCE_W2.json}. The
 * first run of the earlier definition is {@code oracle/K8_ACCEPTANCE_W1.json} and stays a recorded miss.
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

    /** Python bermudan_k8.bermudan_ladder (spec 0.2.0) on the aadladder_g-0001..0003 inputs, grid 41/20 (2026-11-19). */
    private static final double[][] PYTHON_41_20 = {
        {22287.53461841767, 0.0, 211358.63631459567, 162687.8910175668, 139306.3793174654, -231877.5339021703,
            -347142.401546213, 0.0, 0.0, 0.0, 0.0, -50599.24923667921, 2228993.5084961606},
        {14219.03198224864, 0.0, 90811.61296827145, 131329.76588168432, 150157.18125350963, -142268.28751103743,
            -277083.57865698315, 0.0, 0.0, 0.0, 0.0, -49394.77704993134, 2086503.2182632545},
        {13716.96718870294, 0.0, -85323.69457718439, -129308.55315145763, -138026.26813797135, 154928.16366504165,
            276491.2939629992, 0.0, 0.0, 0.0, 0.0, -48789.9281811259, 2034661.6889618998},
    };

    @Test
    void matchesPythonOnSmallGrid() throws IOException {
        for (int k = 0; k < 3; k++) {
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

    /** Spec step 5, worked example: f = (-1, 0, 1) gives E, 1/18, V; and its mirror image. */
    @Test
    void smoothingWorkedExample() {
        double[][] v = {{0.0}, {0.0}, {0.0}};
        double[][] got = BermudanK8.smoothedMax(v, new double[][] {{1.0}, {0.0}, {-1.0}});
        assertEquals(1.0, got[0][0]);
        assertEquals(1.0 / 18, got[1][0], 1e-16);
        assertEquals(0.0, got[2][0]);
        double[][] w = BermudanK8.smoothedMax(v, new double[][] {{-1.0}, {0.0}, {1.0}});
        assertEquals(0.0, w[0][0]);
        assertEquals(1.0 / 18, w[1][0], 1e-16);
        assertEquals(1.0, w[2][0]);
    }

    /** {@code M(p, q)} against a fine midpoint sum on the four branches and at their joins. */
    @Test
    void hatPartClosedForm() {
        double[][] cases = {{1, 2}, {1, -0.5}, {-0.5, 1}, {-1, -2}, {0, 1}, {1, 0}, {0, -1}};
        int n = 200_000;
        for (double[] c : cases) {
            double want = 0;
            for (int i = 0; i < n; i++) {
                double u = (i + 0.5) / n;
                want += (1 - u) * Math.max(c[0] + (c[1] - c[0]) * u, 0.0);
            }
            want /= n;
            double got = BermudanK8.hatPart(new double[] {c[0]}, new double[] {c[1]})[0];
            assertEquals(want, got, 1e-9, c[0] + "," + c[1]);
        }
    }

    /**
     * Away from the crossing the smoothing is the pointwise max: with a cubic V and E = 0, nodes two or more cells
     * inside V &gt; 0 keep V, nodes inside V &lt; 0 get E; the four nodes around the crossing change.
     */
    @Test
    void smoothingKeepsThePointwiseMaxAwayFromTheCrossing() {
        int n = 41;
        double[][] v = new double[n][1];
        double[] f = new double[n];
        int j = -1;
        for (int i = 0; i < n; i++) {
            double x = -1.0 + 2.0 * i / (n - 1);
            f[i] = (x - 0.013) * (1 + 0.3 * x + 0.2 * x * x);
            v[i][0] = f[i];
            if (j < 0 && f[i] > 0) {
                j = i;
            }
        }
        double[][] got = BermudanK8.smoothedMax(v, new double[n][1]);
        for (int i = 0; i < n - 2; i++) {
            if (i >= j + 2) {
                assertEquals(f[i], got[i][0], 1e-14, "node " + i);
            } else if (i < j - 2) {
                assertEquals(0.0, got[i][0], "node " + i);
            } else {
                assertTrue(got[i][0] != Math.max(f[i], 0.0), "node " + i);
            }
        }
    }

    /** KR-18 a: curve nodes the price does not depend on (0.4986 years, and those after the last payment) give 0. */
    @Test
    void curveNodesThePriceDoesNotDependOnGiveExactZeros() throws IOException {
        for (int index = 0; index < 3; index++) {
            double[] d = ladder(ladderCase(index), 41, 20).dDiscountFactors();
            for (int k = 0; k < d.length; k++) {
                assertEquals(k == 0 || k >= 6, d[k] == 0.0, index + "/" + k);
            }
        }
    }

    /** Time-only refinement (41 nodes; 10, 20, 40 steps a year): observed order 2 on the price and every entry. */
    @Test
    void timeOrderIsTwoOnEveryEntry() throws IOException {
        Case c = ladderCase(0);
        double[][] rows = {row(ladder(c, 41, 10)), row(ladder(c, 41, 20)), row(ladder(c, 41, 40))};
        for (int k : new int[] {0, 2, 3, 4, 5, 6, 11, 12}) {
            StageK.Richardson rc = StageK.richardsonCheck(new double[] {rows[0][k], rows[1][k], rows[2][k]}, 2.0, 2.0);
            assertEquals("OK", rc.status(), "entry " + k);
            assertEquals(2.0, rc.observedOrder(), 0.1, "entry " + k);
        }
    }

    /**
     * Space-only refinement on grids that are not nested (60 to 160 cells against 320): the error times cells^2 is the
     * same on every grid to 10% for the price and every entry (the property the cell average of the first definition
     * lacked).
     */
    @Test
    void spaceErrorIsSmoothSecondOrder() throws IOException {
        Case c = ladderCase(0);
        double[] ref = row(ladder(c, 321, 20));
        int[] grids = {61, 81, 101, 131, 161};
        int[] judged = {0, 2, 3, 4, 5, 6, 11, 12};
        double[][] scaled = new double[grids.length][judged.length];
        for (int g = 0; g < grids.length; g++) {
            double[] r = row(ladder(c, grids[g], 20));
            double c2 = Math.pow(grids[g] - 1, 2);
            for (int q = 0; q < judged.length; q++) {
                scaled[g][q] = (r[judged[q]] - ref[judged[q]]) * c2 / (1 - c2 / (320.0 * 320.0));
            }
        }
        for (int q = 0; q < judged.length; q++) {
            double mean = 0;
            for (double[] row : scaled) {
                mean += row[q] / grids.length;
            }
            for (double[] row : scaled) {
                assertTrue(Math.abs(row[q] - mean) <= 0.1 * Math.abs(mean), "entry " + judged[q]);
            }
        }
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
     * [1.5, 2.5] on the price and every ladder entry that is not exactly zero on all three grids. The values must also
     * equal the Python record {@code oracle/K8_ACCEPTANCE_W2.json} to 1e-9 of the row scale.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "QF_K8_ACCEPTANCE", matches = "1")
    void acceptance3ObservedOrder() throws IOException {
        Map<?, ?> record = (Map<?, ?>) Json.parse(Files.readString(ROOT.resolve("oracle/K8_ACCEPTANCE_W2.json")))
                .value();
        Map<?, ?> pyValues = (Map<?, ?>) record.get("values");
        List<String> bad = new ArrayList<>();
        double worstGap = 0;
        for (int index = 0; index < 3; index++) {
            Case c = ladderCase(index);
            List<double[]> rows = new ArrayList<>();
            int[][] grids = {{201, 100}, {401, 200}, {801, 400}};
            Map<?, ?> py = (Map<?, ?>) pyValues.get("aadladder_g-000" + (index + 1));
            for (int g = 0; g < 3; g++) {
                double[] r = row(ladder(c, grids[g][0], grids[g][1]));
                rows.add(r);
                double[] p = reals(py.get(grids[g][0] + "/" + grids[g][1]));
                double scale = 0;
                for (double x : p) {
                    scale = Math.max(scale, Math.abs(x));
                }
                for (int k = 0; k < r.length; k++) {
                    worstGap = Math.max(worstGap, Math.abs(r[k] - p[k]) / scale);
                }
            }
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
        System.out.println("K-8 acceptance 3 (Java): failures=" + bad + " max_gap_vs_python_relative_to_row_scale="
                + worstGap);
        assertTrue(worstGap <= 1e-9, "Java differs from the Python record by " + worstGap);
        assertTrue(bad.isEmpty(), "K-8 acceptance 3 fails on " + bad.size() + " entries (KR-8, K-QB)");
    }

}
