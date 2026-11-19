package org.quantforge.micro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.quantforge.micro.MicroEstimators.Estimate;

/**
 * The seven planted-recovery tests and the 200-seed coverage run, exactly as
 * {@code specifications/09-microstructure/micro-estimators.md} fixes them (HR-70, HR-71): draws from
 * {@code numpy.random.default_rng(seed)} (ported in {@link NumpyRng}) in the listed order; pass within 3 SE; seed
 * 20261118 + j for test j; seeds 70000..70199 with at most 4 misses. As the streams are numpy's, the Java estimates and
 * misses are the Python tests' own; the miss lists below are the Python build's (2026-11-18).
 */
class MicroEstimatorsRecoveryTest {
    private static boolean hit(Estimate e, double truth) {
        return Math.abs(e.value() - truth) <= 3 * e.se();
    }

    private static MicroEstimators.Sample impact(NumpyRng rng, double lam, int n) {
        double[] x = new double[n];
        double[] y = new double[n];
        for (int i = 0; i < n; i++) {
            long s = rng.choice(new long[] {-1, 1});
            long q = rng.integers(1, 101);
            double e = rng.normal(0, 0.05);
            x[i] = s * q;
            y[i] = lam * s * q + e;
        }
        return new MicroEstimators.Sample(x, y);
    }

    static boolean r1(NumpyRng rng) {
        double lam = 2.5;
        double t = 3600.0;
        return hit(MicroEstimators.arrivalRate(rng.poisson(lam * t), t), lam);
    }

    static boolean r2(NumpyRng rng) {
        double theta = 0.4;
        double fill = 0.1;
        MicroEstimators.Order[] rows = new MicroEstimators.Order[5000];
        for (int i = 0; i < rows.length; i++) {
            double life = rng.exponential(1 / (theta + fill));
            rows[i] = new MicroEstimators.Order(life, rng.random() < theta / (theta + fill));
        }
        return hit(MicroEstimators.cancelRate(rows), theta);
    }

    static boolean r3(NumpyRng rng) {
        double kappa = 0.3;
        double s0 = 5.0;
        double sinf = 1.0;
        double[][] pts = new double[21][];
        for (int t = 0; t <= 20; t++) {
            pts[t] = new double[] {t, sinf + (s0 - sinf) * Math.exp(-kappa * t) * Math.exp(rng.normal(0, 0.05))};
        }
        return hit(MicroEstimators.resilience(sinf, pts), kappa);
    }

    static boolean r4(NumpyRng rng) {
        double alpha = 0.15;
        double d0 = 1000.0;
        double[][] lv = new double[31][];
        for (int k = 0; k <= 30; k++) {
            lv[k] = new double[] {k, d0 * Math.exp(-alpha * k) * Math.exp(rng.normal(0, 0.1))};
        }
        return hit(MicroEstimators.liquidityDecay(lv), alpha);
    }

    static boolean r5(NumpyRng rng) {
        MicroEstimators.Sample s = impact(rng, 0.002, 2000);
        return hit(MicroEstimators.adverseSelection(s.x(), s.y()), 0.002);
    }

    static boolean r6(NumpyRng rng) {
        MicroEstimators.Sample calm = impact(rng, 0.001, 1000);
        MicroEstimators.Sample stressed = impact(rng, 0.004, 1000);
        Map<String, Estimate> r = MicroEstimators.regimeImpact(Map.of("calm", calm, "stressed", stressed)).regimes();
        return hit(r.get("calm"), 0.001) && hit(r.get("stressed"), 0.004);
    }

    static boolean r7(NumpyRng rng) {
        double[] passive = new double[1000];
        double[] aggressive = new double[1000];
        for (int i = 0; i < 1000; i++) {
            passive[i] = rng.normal(-1, 2);
        }
        for (int i = 0; i < 1000; i++) {
            aggressive[i] = rng.normal(1.5, 2);
        }
        return hit(MicroEstimators.passiveVsAggressive(passive, aggressive), 2.5);
    }

    private static final List<Predicate<NumpyRng>> RECOVERY = List.of(
            MicroEstimatorsRecoveryTest::r1, MicroEstimatorsRecoveryTest::r2, MicroEstimatorsRecoveryTest::r3,
            MicroEstimatorsRecoveryTest::r4, MicroEstimatorsRecoveryTest::r5, MicroEstimatorsRecoveryTest::r6,
            MicroEstimatorsRecoveryTest::r7);

    /** The Python build's coverage-run misses per test (python/tests/test_stage_h_micro.py, numpy 2.5.4). */
    private static final List<List<Integer>> PYTHON_MISSES = List.of(
            List.of(70075), List.of(), List.of(), List.of(70190), List.of(), List.of(), List.of(70028));

    @ParameterizedTest
    @ValueSource(ints = {1, 2, 3, 4, 5, 6, 7})
    void singleSeed(int j) {
        assertTrue(RECOVERY.get(j - 1).test(new NumpyRng(20261118L + j)), "seed " + (20261118L + j));
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 2, 3, 4, 5, 6, 7})
    void coverage(int j) {
        List<Integer> misses = new ArrayList<>();
        for (int s = 70000; s < 70200; s++) {
            if (!RECOVERY.get(j - 1).test(new NumpyRng(s))) {
                misses.add(s);
            }
        }
        assertTrue(misses.size() <= 4, misses::toString);
        assertEquals(PYTHON_MISSES.get(j - 1), misses);
    }
}
