package org.quantforge.execution;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Random;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;
import org.quantforge.core.QfError;
import org.quantforge.execution.Execution.Mode;
import org.quantforge.execution.Execution.Side;

/** Every golden row of the stage H wave 1 specs (HR-1 to HR-10), plus the property tests they list. */
class ExecutionTest {
    private static final Execution.AcParams P = new Execution.AcParams(1e6, 5, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7);

    private static String code(Executable e) {
        return assertThrows(QfError.class, e).code();
    }

    private static void close(double expected, double actual, double rel) {
        assertEquals(expected, actual, rel * Math.max(1.0, Math.abs(expected)));
    }

    // ---- schedules.md ----

    @Test
    void vwapSubnormalWeightKeepsTheOrder() {
        assertArrayEquals(new double[] {1.5}, Execution.vwap(1.5, new double[] {5e-324}, Mode.CONTINUOUS), 0.0);
        assertArrayEquals(new double[] {1.5, 1.5},
                Execution.vwap(3, new double[] {5e-324, 5e-324}, Mode.CONTINUOUS), 0.0);
    }

    @Test
    void scheduleGoldens() {
        assertArrayEquals(new double[] {334, 333, 333}, Execution.twap(1000, 3, Mode.UNITS)); // sched_h-0001
        assertArrayEquals(new double[] {250, 250, 250, 250}, Execution.twap(1000, 4, Mode.CONTINUOUS)); // 0002
        assertArrayEquals(new double[] {100, 200, 300, 400},
                Execution.vwap(1000, new double[] {1, 2, 3, 4}, Mode.CONTINUOUS), 1e-12); // 0003
        assertArrayEquals(new double[] {4, 3, 3}, Execution.vwap(10, new double[] {1, 1, 1}, Mode.UNITS)); // 0004
        Execution.Pov a = Execution.pov(1000, 0.2, new double[] {1000, 2000, 4000}, Mode.UNITS); // 0005
        assertArrayEquals(new double[] {250, 500, 250}, a.slices());
        assertEquals(0, a.residual());
        assertEquals(1000, a.filled());
        Execution.Pov b = Execution.pov(1000, 0.1, new double[] {900, 900}, Mode.CONTINUOUS); // 0006
        assertArrayEquals(new double[] {100, 100}, b.slices(), 1e-10);
        assertEquals(800, b.residual(), 1e-10);
        assertEquals("E_DOMAIN", code(() -> Execution.pov(1000, 1.0, new double[] {1}, Mode.UNITS))); // 0007
        assertEquals("E_DOMAIN", code(() -> Execution.vwap(1000, new double[] {0, 0}, Mode.UNITS))); // 0008
    }

    @Test
    void scheduleErrors() {
        assertEquals("E_INPUT", code(() -> Execution.twap(0, 3, Mode.UNITS)));
        assertEquals("E_INPUT", code(() -> Execution.twap(10.5, 3, Mode.UNITS)));
        assertEquals("E_INPUT", code(() -> Execution.twap(10, 0, Mode.UNITS)));
        assertEquals(3, Execution.twap(10.5, 3, Mode.CONTINUOUS).length);
        assertEquals("E_INPUT", code(() -> Execution.vwap(10, new double[] {}, Mode.UNITS)));
        assertEquals("E_DOMAIN", code(() -> Execution.vwap(10, new double[] {1, -1}, Mode.UNITS)));
        assertEquals("E_DOMAIN", code(() -> Execution.pov(10, 0, new double[] {1}, Mode.UNITS)));
        assertEquals("E_DOMAIN", code(() -> Execution.pov(10, 0.5, new double[] {-1}, Mode.UNITS)));
        assertEquals("E_INPUT", code(() -> Execution.pov(-1, 0.5, new double[] {1}, Mode.UNITS)));
    }

    @Test
    void slicesSumExactlyAndPovParticipationHolds() {
        Random rnd = new Random(7);
        for (int trial = 0; trial < 300; trial++) {
            int n = 1 + rnd.nextInt(40);
            double x = 1 + rnd.nextInt(1_000_000);
            double[] w = new double[n];
            for (int i = 0; i < n; i++) {
                w[i] = rnd.nextInt(4) == 0 ? 0 : rnd.nextDouble() * 10;
            }
            w[rnd.nextInt(n)] += 1;
            for (Mode m : Mode.values()) {
                double tol = m == Mode.UNITS ? 0 : 1e-12 * x;
                assertEquals(x, sum(Execution.twap(x, n, m)), tol);
                double[] v = Execution.vwap(x, w, m);
                assertEquals(x, sum(v), tol);
                for (double s : v) {
                    assertTrue(s >= 0);
                    if (m == Mode.UNITS) {
                        assertEquals(Math.rint(s), s);
                    }
                }
            }
            double p = 0.01 + 0.9 * rnd.nextDouble();
            double[] mv = new double[n];
            for (int i = 0; i < n; i++) {
                mv[i] = rnd.nextDouble() * 1e5;
            }
            Execution.Pov r = Execution.pov(x, p, mv, Mode.CONTINUOUS);
            assertEquals(x, r.filled() + r.residual(), 1e-9 * x);
            double left = x;
            for (int i = 0; i < n; i++) {
                if (r.slices()[i] < left - 1e-9 * x && mv[i] > 0) { // not capped
                    assertEquals(p, r.slices()[i] / (r.slices()[i] + mv[i]), 1e-12);
                }
                left -= r.slices()[i];
            }
            Execution.Pov u = Execution.pov(x, p, mv, Mode.UNITS);
            assertEquals(x, u.filled() + u.residual());
        }
    }

    private static double sum(double[] a) {
        double s = 0;
        for (double x : a) {
            s += x;
        }
        return s;
    }

    // ---- almgren-chriss.md ----

    @Test
    void acGoldens() {
        Execution.AcTrajectory r1 = Execution.acTrajectory(P, 0); // ac_h-0001
        assertArrayEquals(new double[] {1e6, 8e5, 6e5, 4e5, 2e5, 0}, r1.holdings());
        close(662_500, r1.expectedCost(), 1e-12);
        close(1.083e12, r1.variance(), 1e-12);
        assertEquals(0, r1.kappa());

        Execution.AcTrajectory r2 = Execution.acTrajectory(P, 1e-6); // ac_h-0002
        close(0.6070761632, r2.kappa(), 1e-10);
        double[] h = {1e6, 541955.5544, 289854.2194, 147897.4878, 62141.8016, 0};
        for (int j = 0; j < h.length; j++) {
            close(h[j], r2.holdings()[j], 1e-9);
        }
        close(911_226.986, r2.expectedCost(), 1e-9);
        close(3.641285721e11, r2.variance(), 1e-9);
        close(1_275_355.558, r2.objective(), 1e-9);

        assertEquals("E_DOMAIN", code(() -> Execution.acTrajectory( // ac_h-0003
                new Execution.AcParams(1e6, 5, 5, 0.95, 0.0625, 2.5e-6, 2 * 2.5e-6 / 1.0), 1e-6)));

        Execution.AcTrajectory r4 = Execution.acTrajectory( // ac_h-0004
                new Execution.AcParams(1e6, 5, 1, 0.95, 0.0625, 2.5e-6, 2.5e-7), 1e-6);
        assertArrayEquals(new double[] {1e6, 0}, r4.holdings());
        close(562_500, r4.expectedCost(), 1e-12);

        Execution.AcTrajectory r5 = Execution.acTrajectory(P, 1e-6); // ac_h-0005, printed [AC00] p. 24
        assertEquals(0.6, r5.kappa(), 0.05);
        assertEquals(3.0, r5.kappa() * 5, 0.25);
        close(3.0353808, r5.kappa() * 5, 1e-8);
    }

    @Test
    void acErrors() {
        assertEquals("E_INPUT", code(() -> Execution.acTrajectory(new Execution.AcParams(1e6, 5, 0, 1, 0, 1e-6, 0), 0)));
        assertEquals("E_DOMAIN", code(() -> Execution.acTrajectory(new Execution.AcParams(1e6, 0, 5, 1, 0, 1e-6, 0), 0)));
        assertEquals("E_DOMAIN", code(() -> Execution.acTrajectory(new Execution.AcParams(1e6, 5, 5, -1, 0, 1e-6, 0), 0)));
        assertEquals("E_DOMAIN", code(() -> Execution.acTrajectory(P, -1e-6)));
        assertEquals("E_INPUT", code(() -> Execution.acFrontier(P, new double[] {})));
    }

    @Test
    void acProperties() {
        for (double lambda : new double[] {1e-8, 1e-6, 1e-5}) {
            Execution.AcTrajectory r = Execution.acTrajectory(P, lambda);
            assertEquals(1e6, sum(r.trades()), 1e-12 * 1e6);
            for (int j = 1; j < 5; j++) {
                assertTrue(r.holdings()[j] < 1e6 * (5 - j) / 5.0);
            }
        }
        Execution.AcTrajectory tiny = Execution.acTrajectory(P, 1e-15); // lambda -> 0 limit
        for (int j = 0; j <= 5; j++) {
            assertEquals(1e6 * (5 - j) / 5.0, tiny.holdings()[j], 1e-9 * 1e6);
        }
        // tau -> 0: kappa_tilde -> sqrt(lambda sigma^2 / eta), error falling like tau ([AC00] eq. (19)).
        double limit = Math.sqrt(1e-6 * 0.95 * 0.95 / 2.5e-6);
        double prev = Double.MAX_VALUE;
        for (long n : new long[] {10, 100, 1000}) {
            double k = Execution.acTrajectory(new Execution.AcParams(1e6, 5, n, 0.95, 0.0625, 2.5e-6, 2.5e-7),
                    1e-6).kappa();
            double err = Math.abs(k - limit);
            assertTrue(err < prev / 5);
            prev = err;
        }
        // HR-6: small y keeps digits, kappa tau ~ sqrt(2 y).
        double y = 1e-14;
        assertEquals(Math.sqrt(2 * y), Execution.kappa(y * 2, 1, 1, 1), 1e-12 * Math.sqrt(2 * y));
        // kappa T > 700: finite and decreasing holdings.
        Execution.AcTrajectory big = Execution.acTrajectory(new Execution.AcParams(1e6, 5, 50, 0.95, 0, 2.5e-6, 0),
                (Math.cosh(20) - 1) * 2 * 2.5e-6 / (0.95 * 0.95 * 0.01));
        assertTrue(big.kappa() * 5 > 700);
        for (int j = 1; j <= 50; j++) {
            assertTrue(Double.isFinite(big.holdings()[j]) && big.holdings()[j] <= big.holdings()[j - 1]);
        }
        assertEquals(1e6, sum(big.trades()), 1e-12 * 1e6);
    }

    @Test
    void frontierIsMonotone() {
        double[] lambdas = {0, 1e-8, 1e-7, 1e-6, 3e-6, 1e-5, 1e-4};
        Execution.AcFrontier f = Execution.acFrontier(P, lambdas);
        for (int i = 1; i < lambdas.length; i++) {
            assertTrue(f.expectedCost()[i] >= f.expectedCost()[i - 1]);
            assertTrue(f.variance()[i] <= f.variance()[i - 1]);
        }
        Execution.AcTrajectory one = Execution.acTrajectory(P, 1e-6);
        assertEquals(one.expectedCost(), f.expectedCost()[3]);
        assertEquals(one.variance(), f.variance()[3]);
    }

    // ---- impact.md ----

    @Test
    void impactGoldens() {
        close(0.002, Execution.impactSqrt(1e5, 1e7, 0.02, 1), 1e-15); // imp_h-0001
        close(0.004, Execution.impactSqrt(4e5, 1e7, 0.02, 1), 1e-15); // imp_h-0002
        Execution.OwOptimal a = Execution.owOptimal(1000, 1, 8); // imp_h-0003
        assertEquals(100, a.initialBlock(), 1e-12);
        assertEquals(100, a.finalBlock(), 1e-12);
        assertEquals(800, a.rate(), 1e-12);
        Execution.OwOptimal b = Execution.owOptimal(100_000, 1, 2.231); // imp_h-0004
        close(23_635.0744504845, b.initialBlock(), 1e-13);
        close(52_729.8510990310, b.rate(), 1e-13);
        assertEquals(100_000, 2 * b.initialBlock() + b.rate() * 1, 1e-9);
        Execution.OwOptimal c = Execution.owOptimal(1000, 1, 1e-9); // rho -> 0: blocks -> X / 2
        assertEquals(500, c.initialBlock(), 1e-6);
        assertEquals("E_DOMAIN", code(() -> Execution.impactSqrt(-1, 1e7, 0.02, 1)));
        assertEquals("E_DOMAIN", code(() -> Execution.impactSqrt(1, 0, 0.02, 1)));
        assertEquals("E_DOMAIN", code(() -> Execution.owOptimal(1, 1, 0)));
        assertEquals("E_INPUT", code(() -> Execution.owOptimal(0, 1, 1)));
    }

    // ---- tca.md ----

    private static Execution.Shortfall tca(Side side, double fees, double[] q, Double vwap) {
        return Execution.shortfall(side, 100, 100.10, 101, 1000, q, new double[] {100.20, 100.30}, fees, vwap);
    }

    @Test
    void tcaGoldens() {
        Execution.Shortfall a = tca(Side.BUY, 5, new double[] {600, 200}, null); // tca_h-0001
        close(80, a.delay(), 1e-12);
        close(100, a.execution(), 1e-12);
        close(200, a.opportunity(), 1e-12);
        close(385, a.total(), 1e-12);
        close(38.5, a.totalBps(), 1e-12);
        assertNull(a.vwapSlippage());
        Execution.Shortfall b = tca(Side.SELL, 0, new double[] {600, 200}, null); // tca_h-0002
        close(-80, b.delay(), 1e-12);
        close(-100, b.execution(), 1e-12);
        close(-200, b.opportunity(), 1e-12);
        close(-380, b.total(), 1e-12);
        assertEquals("E_INPUT", code(() -> tca(Side.BUY, 0, new double[] {600, 600}, null))); // tca_h-0003
        assertEquals("E_DOMAIN", code(() -> Execution.shortfall(Side.BUY, 0, 1, 1, 10, new double[] {}, new double[] {},
                0, null)));
        Execution.Shortfall v = tca(Side.BUY, 0, new double[] {600, 200}, 100.0);
        close(800 * (100.225 - 100), v.vwapSlippage(), 1e-12);
    }

    @Test
    void tcaDecompositionSums() {
        Random rnd = new Random(11);
        for (int trial = 0; trial < 500; trial++) {
            int n = rnd.nextInt(8);
            double[] q = new double[n];
            double[] p = new double[n];
            double x = 0;
            for (int i = 0; i < n; i++) {
                q[i] = 1 + rnd.nextInt(1000);
                p[i] = 50 + 100 * rnd.nextDouble();
                x += q[i];
            }
            boolean full = rnd.nextBoolean() && n > 0;
            x += full ? 0 : 1 + rnd.nextInt(1000);
            Side side = rnd.nextBoolean() ? Side.BUY : Side.SELL;
            double fees = rnd.nextDouble() * 10;
            double pd = 50 + 100 * rnd.nextDouble();
            Execution.Shortfall r = Execution.shortfall(side, pd, 50 + 100 * rnd.nextDouble(),
                    50 + 100 * rnd.nextDouble(), x, q, p, fees, null);
            double parts = r.delay() + r.execution() + r.opportunity() + fees;
            assertEquals(r.total(), parts, 1e-10 * Math.max(1, Math.abs(r.total())));
            assertEquals(r.total() / (x * pd) * 1e4, r.totalBps(), 1e-12 * Math.max(1, Math.abs(r.totalBps())));
            if (full) {
                assertEquals(0, r.opportunity());
            }
        }
    }

    // ---- avellaneda-stoikov.md ----

    @Test
    void asGoldens() {
        Execution.Quotes a = Execution.asQuotes(100, 2, 0.1, 2, 1, 1.5); // as_h-0001
        close(99.2, a.reservation(), 1e-12);
        close(1.6907704228, a.spread(), 1e-10);
        close(98.3546147886, a.bid(), 1e-10);
        close(100.0453852114, a.ask(), 1e-10);
        Execution.Quotes b = Execution.asQuotes(100, 0, 0.1, 2, 1, 1.5); // as_h-0002
        assertEquals(100, b.reservation());
        close(99.1546147886, b.bid(), 1e-10);
        close(100.8453852114, b.ask(), 1e-10);
        Execution.Quotes c = Execution.asQuotes(100, 2, 0.1, 2, 0, 1.5); // as_h-0003
        assertEquals(100, c.reservation());
        close(1.2907704228, c.spread(), 1e-10);
        assertEquals("E_DOMAIN", code(() -> Execution.asQuotes(100, 2, 0, 2, 1, 1.5))); // as_h-0004
        Execution.Quotes t1 = Execution.asQuotes(100, 0, 0.1, 2, 0.5, 1.5); // as_h-0005
        close(1.4907704228, t1.spread(), 1e-10);
        assertEquals(1.49, t1.spread(), 0.005);
        Execution.Quotes t2 = Execution.asQuotes(100, 0, 0.01, 2, 0.5, 1.5); // as_h-0006
        close(1.3489085437, t2.spread(), 1e-10);
        assertEquals(1.35, t2.spread(), 0.005);
        Execution.Quotes t3 = Execution.asQuotes(100, 0, 1, 2, 0.5, 1.5); // as_h-0007
        close(3.0216512475, t3.spread(), 1e-10);
        assertEquals(3.02, t3.spread(), 0.005);
        assertEquals("E_DOMAIN", code(() -> Execution.asQuotes(100, 2, 0.1, 2, 1, 0)));
    }

    @Test
    void asProperties() {
        assertEquals(2 / 1.5, Execution.asQuotes(100, 0, 1e-12, 2, 1, 1.5).spread(), 1e-10);
        double prev = Double.MAX_VALUE;
        for (int q = -5; q <= 5; q++) {
            Execution.Quotes r = Execution.asQuotes(100, q, 0.1, 2, 1, 1.5);
            assertTrue(r.reservation() < prev);
            close(100 - q * 0.4, r.reservation(), 1e-13);
            close(r.spread(), r.ask() - r.bid(), 1e-13);
            prev = r.reservation();
        }
    }
}
