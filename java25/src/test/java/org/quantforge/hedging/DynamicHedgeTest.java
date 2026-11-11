package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Random;
import net.jqwik.api.Example;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.quantforge.core.QfError;

/** Wave 4b: the spec's property tests for the replay and the statistics, and every validation path. */
class DynamicHedgeTest {

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    @Property(tries = 100)
    void aPerfectOffsetScoresOneOnEveryMeasure(@ForAll long seed) {
        Random rnd = new Random(seed);
        int n = 3 + rnd.nextInt(30);
        double[] x = new double[n];
        double[] y = new double[n];
        for (int i = 0; i < n; i++) {
            x[i] = 100 * rnd.nextGaussian() + 5;
            y[i] = -x[i];
        }
        DynamicHedge.Effectiveness e = DynamicHedge.effectiveness(x, y);
        assertEquals(1.0, e.dollarOffset(), 1e-12);
        assertEquals(-1.0, e.regressionSlope(), 1e-12);
        assertEquals(1.0, e.regressionR2(), 1e-12);
        assertEquals(1.0, e.varianceReduction(), 1e-12);
    }

    @Property(tries = 50)
    void constantSpotReplayEndsAtTheOptionsTimeDecay(@ForAll long seed) {
        // Handover correction e6605a2: the replay is tested directly; with zero rates and dividends the portfolio
        // ends at quantity (V_last - V_0).
        Random rnd = new Random(seed);
        boolean call = rnd.nextBoolean();
        double k = 80 + 40 * rnd.nextDouble();
        double s = 80 + 40 * rnd.nextDouble();
        double t = 0.2 + rnd.nextDouble();
        double q = 100 * rnd.nextGaussian();
        int m = 4 + rnd.nextInt(20);
        double[] times = new double[m];
        double[] spots = new double[m];
        for (int i = 0; i < m; i++) {
            times[i] = t * i / (m - 1);
            spots[i] = s;
        }
        times[m - 1] = t; // exactly at expiry, whatever the rounding of t (m-1)/(m-1)
        // The hedge leg is zero only in exact arithmetic; in doubles it carries rounding noise, so whether the I-31
        // zero-variance rule fires here is open (spec question J-I5) and is not asserted.
        // Replay by hand with the same marks: cash never earns, shares never pay, rebalances are at the same spot.
        double v0 = DynamicHedge.valueDelta(call, s, k, t, 0, 0, 0.2)[0];
        double vLast = DynamicHedge.valueDelta(call, s, k, 0.0, 0, 0, 0.2)[0];
        double[] path = spots.clone();
        path[m - 1] = s * 1.01; // a final move gives the statistics variance; the earlier steps are pure decay
        DynamicHedge.Backtest b = DynamicHedge.backtest(call, k, t, q, 0, 0, 0.2, times, path);
        double[] pi = b.portfolioValues();
        double vPen = b.optionValues()[m - 2];
        assertEquals(q * (vPen - v0), pi[m - 2], 1e-9 * Math.max(1.0, Math.abs(q * v0)));
        assertEquals(DynamicHedge.valueDelta(call, s * 1.01, k, 0.0, 0, 0, 0.2)[0], b.optionValues()[m - 1], 0.0);
        assertEquals(vLast, DynamicHedge.valueDelta(call, s, k, -1.0, 0, 0, 0.2)[0], 0.0);
    }

    @Example
    void replayFollowsTheCashAccountOrder() {
        double[] times = {0, 0.1, 0.2, 0.3};
        double[] spots = {100, 102, 99, 101};
        DynamicHedge.Backtest b = DynamicHedge.backtest(true, 100, 0.5, -10, 0.03, 0.02, 0.2, times, spots);
        double[] v = b.optionValues();
        double[] h = b.shares();
        double cash = 10 * v[0] - h[0] * 100;
        cash = cash * Math.exp(0.003) + h[0] * 100 * (Math.exp(0.002) - 1);
        assertEquals(-10 * v[1] + h[0] * 102 + cash, b.portfolioValues()[1], 1e-12);
        cash -= (h[1] - h[0]) * 102;
        cash = cash * Math.exp(0.003) + h[1] * 102 * (Math.exp(0.002) - 1);
        assertEquals(-10 * v[2] + h[1] * 99 + cash, b.portfolioValues()[2], 1e-12);
        assertEquals(0.0, b.portfolioValues()[0], 1e-12);
        assertEquals(b.portfolioValues()[3], b.finalPnl(), 0.0);
        assertEquals(3, h.length);
    }

    @Example
    void putValuesAndPayoffAtExpiry() {
        double[] vd = DynamicHedge.valueDelta(false, 90, 100, 0.0, 0.03, 0.01, 0.2);
        assertEquals(10.0, vd[0], 0.0);
        double[] c = DynamicHedge.valueDelta(true, 100, 100, 1.0, 0.03, 0.01, 0.2);
        double[] p = DynamicHedge.valueDelta(false, 100, 100, 1.0, 0.03, 0.01, 0.2);
        assertEquals(100 * Math.exp(-0.01) - 100 * Math.exp(-0.03), c[0] - p[0], 1e-12);
        assertEquals(Math.exp(-0.01), c[1] - p[1], 1e-14);
    }

    @Example
    void checks() {
        double[] t = {0, 0.1, 0.2, 0.3};
        double[] s = {100, 101, 99, 100};
        assertEquals("E_INPUT", code(() -> DynamicHedge.backtest(true, 100, 1, 1, 0, 0, 0.2, t, new double[3])));
        assertEquals("E_INPUT", code(() -> DynamicHedge.backtest(true, 100, 1, 1, 0, 0, 0.2, new double[] {0, 1, 2},
                new double[] {1, 1, 1})));
        assertEquals("E_INPUT", code(() -> DynamicHedge.backtest(true, 100, 1, 1, 0, 0, 0.2,
                new double[] {0.1, 0.2, 0.3, 0.4}, s)));
        assertEquals("E_INPUT", code(() -> DynamicHedge.backtest(true, 100, 1, 1, 0, 0, 0.2,
                new double[] {0, 0.2, 0.2, 0.4}, s)));
        assertEquals("E_INPUT", code(() -> DynamicHedge.backtest(true, 100, 0.25, 1, 0, 0, 0.2, t, s)));
        assertEquals("E_DOMAIN", code(() -> DynamicHedge.backtest(true, 100, 1, 1, 0, 0, 0.2, t,
                new double[] {100, 0, 99, 100})));
        assertEquals("E_DOMAIN", code(() -> DynamicHedge.backtest(true, 0, 1, 1, 0, 0, 0.2, t, s)));
        assertEquals("E_DOMAIN", code(() -> DynamicHedge.backtest(true, 100, 0.3, 1, 0, 0, 0, t, s)));
        assertEquals("E_DOMAIN", code(() -> DynamicHedge.backtest(true, 100, 1, 0, 0, 0, 0.2, t, s)));
        assertEquals("E_INPUT", code(() -> DynamicHedge.effectiveness(new double[] {1, 2, 3}, new double[] {1, 2})));
        assertEquals("E_INPUT", code(() -> DynamicHedge.effectiveness(new double[] {1, 2}, new double[] {1, 2})));
        assertEquals("E_DOMAIN", code(() -> DynamicHedge.effectiveness(new double[] {1, -2, 1},
                new double[] {1, 2, 3})));
        assertEquals("E_DOMAIN", code(() -> DynamicHedge.effectiveness(new double[] {0.1, 0.1, 0.1},
                new double[] {1, 2, 3})));
        assertEquals("E_DOMAIN", code(() -> DynamicHedge.effectiveness(new double[] {1, 2, 3},
                new double[] {2, 2, 2})));
    }
}
