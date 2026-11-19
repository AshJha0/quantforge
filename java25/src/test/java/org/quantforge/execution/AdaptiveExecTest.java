package org.quantforge.execution;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Rng;
import org.quantforge.execution.AdaptiveExec.PairMode;
import org.quantforge.execution.Execution.Mode;
import org.quantforge.execution.Execution.Side;
import org.quantforge.micro.LitMatching;

/** Acceptance tests of adaptive-algos.md (1 to 4) and tca-pretrade.md (1, 2); seed 20261118. Goldens run in GoldenSuiteTest. */
class AdaptiveExecTest {
    private static final long SEED = 20261118L;

    /** Draws as the Python test's helper: u in [a, b) from the top 53 bits, i in [a, b] by unsigned modulo. */
    private static final class U {
        final Rng g;

        U(long seed) {
            g = Rng.seeded(seed, 0);
        }

        double u(double a, double b) {
            return a + (b - a) * ((g.nextLong() >>> 11) * 0x1p-53);
        }

        long i(long a, long b) {
            return a + Long.remainderUnsigned(g.nextLong(), b - a + 1);
        }

        Side side() {
            return (g.nextLong() & 1) != 0 ? Side.BUY : Side.SELL;
        }
    }

    private static boolean rel(double got, double exp) {
        return Math.abs(got - exp) <= 1e-12 * Math.max(1.0, Math.abs(exp));
    }

    private static double sum(double[] x) {
        double s = 0;
        for (double v : x) {
            s += v;
        }
        return s;
    }

    @Test
    void arrivalIdentities() {
        U r = new U(SEED);
        for (int t = 0; t < 1000; t++) {
            long n = r.i(1, 60);
            double k = r.u(0, 2);
            double x = r.i(1, 1_000_000_000L);
            double[] c = AdaptiveExec.arrival(x, n, k, Mode.CONTINUOUS);
            assertTrue(rel(sum(c), x));
            for (int j = 1; j < c.length; j++) {
                assertTrue(c[j - 1] > c[j], n + " " + k);
            }
            double[] u = AdaptiveExec.arrival(x, n, k, Mode.UNITS);
            assertEquals(x, sum(u));
            for (int j = 0; j < u.length; j++) {
                assertTrue(Math.abs(u[j] - c[j]) < 1 + 1e-9 * x); // HR-67
            }
        }
        assertArrayEquals(Execution.twap(1000, 3, Mode.UNITS), AdaptiveExec.arrival(1000, 3, 0, Mode.UNITS));
        for (int t = 0; t < 1000; t++) {
            long n = r.i(1, 500);
            double x = r.i(1, 1_000_000_000L);
            assertArrayEquals(Execution.twap(x, n, Mode.UNITS), AdaptiveExec.arrival(x, n, 0, Mode.UNITS));
            assertArrayEquals(Execution.twap(x, n, Mode.CONTINUOUS), AdaptiveExec.arrival(x, n, 0, Mode.CONTINUOUS));
        }
    }

    @Test
    void closeIdentity() {
        U r = new U(SEED + 2);
        for (int t = 0; t < 1000; t++) {
            double[] w = new double[(int) r.i(1, 30)];
            for (int j = 0; j < w.length; j++) {
                w[j] = r.u(0, 5);
            }
            double x = r.i(1, 10_000_000);
            double v = r.u(0, 1e7);
            double p = r.u(0, 1);
            AdaptiveExec.Close c = AdaptiveExec.close(x, v, p, w, Mode.CONTINUOUS);
            assertTrue(rel(c.auctionQuantity() + sum(c.slices()), x));
            AdaptiveExec.Close u = AdaptiveExec.close(x, v, p, w, Mode.UNITS);
            assertEquals(x, u.auctionQuantity() + sum(u.slices()));
        }
    }

    @Test
    void basketIdentities() {
        U r = new U(SEED + 3);
        for (int t = 0; t < 1000; t++) {
            long n = r.i(1, 40);
            AdaptiveExec.Leg[] legs = new AdaptiveExec.Leg[(int) r.i(1, 8)];
            for (int k = 0; k < legs.length; k++) {
                legs[k] = new AdaptiveExec.Leg(r.side(), r.i(1, 1_000_000), r.u(1, 1000));
            }
            AdaptiveExec.Basket c = AdaptiveExec.basket(legs, n, Mode.CONTINUOUS);
            double[] cash = c.cashImbalance();
            for (int k = 0; k < legs.length; k++) {
                assertTrue(rel(sum(c.slices()[k]), legs[k].quantity()));
            }
            for (int j = 0; j < n; j++) {
                assertTrue(Math.abs(cash[j] - (j + 1.0) / n * cash[(int) n - 1]) <= 1e-12 * c.grossNotional());
            }
            AdaptiveExec.Basket u = AdaptiveExec.basket(legs, n, Mode.UNITS);
            for (int k = 0; k < legs.length; k++) {
                assertEquals(legs[k].quantity(), sum(u.slices()[k]));
            }
        }
        AdaptiveExec.Leg[] zero = {new AdaptiveExec.Leg(Side.BUY, 300, 10), new AdaptiveExec.Leg(Side.BUY, 200, 20),
            new AdaptiveExec.Leg(Side.SELL, 700, 10)};
        for (double ci : AdaptiveExec.basket(zero, 7, Mode.CONTINUOUS).cashImbalance()) {
            assertTrue(Math.abs(ci) <= 1e-9);
        }
    }

    @Test
    void pairIdentitiesAndBounds() {
        U r = new U(SEED + 4);
        for (int t = 0; t < 1000; t++) {
            long n = r.i(1, 40);
            double qa = r.i(1, 1_000_000);
            double pa = r.u(1, 1000);
            double pb = r.u(1, 1000);
            Side sa = r.side();
            Side sb = sa == Side.BUY ? Side.SELL : Side.BUY;
            AdaptiveExec.Pair c = AdaptiveExec.pair(sa, qa, pa, sb, pb, PairMode.CASH_BALANCED, null, n,
                    Mode.CONTINUOUS);
            assertTrue(rel(sum(c.slicesA()), qa));
            assertTrue(rel(sum(c.slicesB()), c.quantityB()));
            for (double x : c.cashImbalance()) {
                assertTrue(Math.abs(x) <= 1e-12 * qa * pa);
            }
            AdaptiveExec.Pair u = AdaptiveExec.pair(sa, qa, pa, sb, pb, PairMode.CASH_BALANCED, null, n, Mode.UNITS);
            assertEquals(qa, sum(u.slicesA()));
            assertEquals(u.quantityB(), sum(u.slicesB()));
            assertEquals(Math.floor(pa / pb * qa + 0.5), u.quantityB());
            for (double x : u.cashImbalance()) {
                assertTrue(Math.abs(x) <= pb / 2 * (1 + 1e-12));
            }
            double h = r.u(0.01, 5);
            AdaptiveExec.Pair hd = AdaptiveExec.pair(sa, qa, pa, r.side(), pb, PairMode.HEDGED, h, n,
                    Mode.CONTINUOUS);
            assertTrue(rel(hd.quantityB(), h * qa));
        }
    }

    /** Rests the planted book on the lit engine, sends the child as an IOC at L; returns [qty, notional] and checks L. */
    @SuppressWarnings("unchecked")
    private static BigDecimal[] litFills(Side side, long[][] book, long limit, double child) {
        String opp = side == Side.BUY ? "SELL" : "BUY";
        List<Map<String, Object>> ev = new ArrayList<>();
        for (int k = 0; k < book.length; k++) {
            Map<String, Object> e = new LinkedHashMap<>();
            e.put("op", "NEW");
            e.put("id", "M" + k);
            e.put("trader", "MM");
            e.put("side", opp);
            e.put("type", "LIMIT");
            e.put("price", BigDecimal.valueOf(book[k][0]).movePointLeft(2).toPlainString());
            e.put("qty", Long.toString(book[k][1]));
            ev.add(e);
        }
        if (child > 0) {
            Map<String, Object> e = new LinkedHashMap<>();
            e.put("op", "NEW");
            e.put("id", "C");
            e.put("trader", "US");
            e.put("side", side.name());
            e.put("type", "IOC");
            e.put("price", BigDecimal.valueOf(limit).movePointLeft(2).toPlainString());
            e.put("qty", new BigDecimal(child).toPlainString());
            ev.add(e);
        }
        Map<String, Object> out = LitMatching.run("0.01", "0.125", ev, Map.of("taker_fee", "0", "maker_rebate", "0"));
        BigDecimal q = BigDecimal.ZERO;
        BigDecimal notional = BigDecimal.ZERO;
        BigDecimal lim = BigDecimal.valueOf(limit).movePointLeft(2);
        for (Map<String, Object> f : (List<Map<String, Object>>) out.get("fills")) {
            if (!"C".equals(f.get("taker_id"))) {
                continue;
            }
            BigDecimal fq = new BigDecimal((String) f.get("qty"));
            BigDecimal fp = new BigDecimal((String) f.get("price"));
            assertTrue(side == Side.BUY ? fp.compareTo(lim) <= 0 : fp.compareTo(lim) >= 0, "fill outside L");
            q = q.add(fq);
            notional = notional.add(fq.multiply(fp));
        }
        return new BigDecimal[] {q, notional};
    }

    @Test
    void liquiditySeekSimulatedBook() {
        U r = new U(SEED);
        for (int t = 0; t < 200; t++) {
            Side side = r.side();
            boolean buy = side == Side.BUY;
            int kb = (int) r.i(1, 5);
            double x = r.i(1, 20_000);
            double alpha = r.i(1, 8) / 8.0; // dyadic: alpha A and the remainders are exact
            long limit = r.i(9_000, 11_000);
            long[][][] bt = new long[kb][][];
            double[][][] books = new double[kb][][];
            for (int b = 0; b < kb; b++) {
                int nl = (int) r.i(5, 20);
                long tick = buy ? limit - r.i(0, 40) : limit + r.i(0, 40);
                long[] ticks = new long[nl];
                for (int l = 0; l < nl; l++) {
                    ticks[l] = tick;
                    tick += (buy ? 1 : -1) * r.i(1, 5);
                }
                bt[b] = new long[nl][];
                books[b] = new double[nl][];
                for (int l = 0; l < nl; l++) {
                    bt[b][l] = new long[] {ticks[l], r.i(1, 2_000)};
                    books[b][l] = new double[] {ticks[l] / 100.0, bt[b][l][1]};
                }
            }
            AdaptiveExec.Seek res = AdaptiveExec.liquiditySeek(side, x, limit / 100.0, alpha, books);
            double remaining = x;
            for (int b = 0; b < kb; b++) {
                double depth = 0;
                long planted = 0;
                for (int l = 0; l < books[b].length; l++) {
                    if (buy ? books[b][l][0] <= limit / 100.0 : books[b][l][0] >= limit / 100.0) {
                        depth += books[b][l][1];
                    }
                    if (buy ? bt[b][l][0] <= limit : bt[b][l][0] >= limit) {
                        planted += bt[b][l][1];
                    }
                }
                assertEquals(planted, depth); // known depth inside L
                double want = Math.min(remaining, alpha * depth);
                double c = res.slices()[b];
                assertTrue(rel(c, want));
                BigDecimal[] lit = litFills(side, bt[b], limit, c);
                assertTrue(rel(lit[0].doubleValue(), want)); // recovered fills equal min(R, alpha A_i)
                Double avg = res.avgPrices()[b];
                if (c > 0) {
                    assertNotNull(avg);
                    assertTrue(rel(avg, lit[1].doubleValue() / lit[0].doubleValue()));
                    double best = books[b][0][0];
                    double lo = buy ? best : limit / 100.0;
                    double hi = buy ? limit / 100.0 : best;
                    assertTrue(lo - 1e-12 <= avg && avg <= hi + 1e-12);
                } else {
                    assertNull(avg);
                }
                remaining -= c;
            }
            assertTrue(rel(res.filled() + res.residual(), x));
        }
    }

    @Test
    void attributionIdentityAndShortfall() {
        U r = new U(SEED);
        for (int t = 0; t < 1000; t++) {
            Side side = r.side();
            double s = side == Side.BUY ? 1 : -1;
            double pd = r.u(1, 1000);
            double m0 = r.u(1, 1000);
            double pc = r.u(1, 1000);
            int nf = (int) r.i(1, 50);
            double[] q = new double[nf];
            double[] p = new double[nf];
            double[] m = new double[nf];
            for (int i = 0; i < nf; i++) {
                q[i] = r.u(1, 1000);
                p[i] = r.u(1, 1000);
                m[i] = r.u(1, 1000);
            }
            double x = sum(q) * r.u(1, 2);
            double fees = r.u(0, 100);
            AdaptiveExec.Attribution a = AdaptiveExec.attribution(side, pd, m0, pc, x, q, p, m, fees);
            double bound = 1e-10 * Math.max(1, Math.abs(a.total()));
            double direct = 0;
            for (int i = 0; i < nf; i++) {
                direct += q[i] * (p[i] - pd);
            }
            assertTrue(Math.abs(a.delay() + a.impact() + a.spread() - s * direct) <= bound);
            Execution.Shortfall sf = Execution.shortfall(side, pd, m0, pc, x, q, p, fees, null);
            assertTrue(Math.abs(a.total() - sf.total()) <= bound);
            assertTrue(Math.abs(a.execution() - sf.execution()) <= bound);
        }
    }

    @Test
    void pretradeMonotonicity() {
        U r = new U(SEED + 5);
        for (int t = 0; t < 1000; t++) {
            double adv = r.u(1e5, 1e8);
            double sig = r.u(0.001, 0.1);
            double a1 = r.u(1, 1000);
            double a2 = r.u(0, 2);
            double a3 = r.u(0.1, 2);
            double a4 = r.u(0, 2);
            double b1 = r.u(0, 1);
            double xa = r.u(1, 1e6);
            double xb = r.u(1, 1e6);
            double pa = r.u(0.01, 0.99);
            double pb = r.u(0.01, 0.99);
            double x1 = Math.min(xa, xb);
            double x2 = Math.max(xa, xb);
            double p1 = Math.min(pa, pb);
            double p2 = Math.max(pa, pb);
            var lo = AdaptiveExec.pretrade(x1, adv, sig, p1, 1, a1, a2, a3, a4, b1, null);
            var bx = AdaptiveExec.pretrade(x2, adv, sig, p1, 1, a1, a2, a3, a4, b1, null);
            var hi = AdaptiveExec.pretrade(x1, adv, sig, p2, 1, a1, a2, a3, a4, b1, null);
            assertTrue(lo.impactBps() <= bx.impactBps() * (1 + 1e-14));
            assertTrue(lo.impactBps() <= hi.impactBps() * (1 + 1e-14));
            assertTrue(lo.timingRiskBps() >= hi.timingRiskBps() * (1 - 1e-14));
        }
    }

    /**
     * HR-121: leg B at an exact half rounds up even when binary64 lands just below it. 0.3 / 0.2 is
     * 1.4999999999999998 in binary64 and 1.5 exactly, so one unit of A needs two of B; 5 x 0.7 / 1.0 = 3.5 needs four.
     */
    @Test
    void pairRoundsAnExactHalfUp() {
        AdaptiveExec.Pair p = AdaptiveExec.pair(Side.BUY, 1, 0.3, Side.SELL, 0.2, PairMode.CASH_BALANCED, null, 1, Mode.UNITS);
        assertEquals(2.0, p.quantityB());
        assertArrayEquals(new double[] {2.0}, p.slicesB());
        assertEquals(-0.1, p.cashImbalance()[0], 1e-15);
        p = AdaptiveExec.pair(Side.BUY, 5, 0.7, Side.SELL, 1.0, PairMode.CASH_BALANCED, null, 1, Mode.UNITS);
        assertEquals(4.0, p.quantityB());
        // a target well away from a half is untouched: 3 x 0.5 / 1.3 = 1.15 rounds to 1
        p = AdaptiveExec.pair(Side.BUY, 3, 0.5, Side.SELL, 1.3, PairMode.CASH_BALANCED, null, 1, Mode.UNITS);
        assertEquals(1.0, p.quantityB());
    }

    /** A bad leg quantity names {@code quantity} as its field in all four builds (adaptive-algos.md). */
    @Test
    void legQuantityErrorNamesQuantity() {
        org.quantforge.core.QfError e = org.junit.jupiter.api.Assertions.assertThrows(org.quantforge.core.QfError.class,
                () -> AdaptiveExec.pair(Side.BUY, 0.0, 50.0, Side.SELL, 25.0, PairMode.CASH_BALANCED, null, 2, Mode.CONTINUOUS));
        assertEquals("quantity", e.field());
        AdaptiveExec.Leg[] legs = {new AdaptiveExec.Leg(Side.BUY, 2.5, 10.0)};
        e = org.junit.jupiter.api.Assertions.assertThrows(org.quantforge.core.QfError.class,
                () -> AdaptiveExec.basket(legs, 2, Mode.UNITS));
        assertEquals("quantity", e.field());
    }
}
