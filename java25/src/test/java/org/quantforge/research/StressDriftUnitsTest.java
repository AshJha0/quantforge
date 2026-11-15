package org.quantforge.research;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigInteger;
import java.time.LocalDate;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;
import org.quantforge.core.Interpolation;
import org.quantforge.core.QfError;

/** Mutation-targeted unit tests for StressDrift; every expected value is derived by hand in the comments. */
class StressDriftUnitsTest {

    private static void err(String code, Executable e) {
        assertEquals(code, assertThrows(QfError.class, e).code());
    }

    private static void err(String code, String field, Executable e) {
        QfError q = assertThrows(QfError.class, e);
        assertEquals(code, q.code());
        assertEquals(field, q.field());
    }

    // --- fsum ---------------------------------------------------------------------------------------

    @Test
    void fsumIsCorrectlyRounded() {
        assertEquals(0.0, StressDrift.fsum(new double[0]));
        assertEquals(1.0, StressDrift.fsum(new double[] {1e100, 1.0, -1e100}));
        double[] tenth = new double[10];
        Arrays.fill(tenth, 0.1);
        assertEquals(1.0, StressDrift.fsum(tenth));
        // exact 1 + 2^-53 + 2^-80 lies above the halfway point: rounds up to 1 + 2^-52.
        double h = Math.scalb(1.0, -53);
        double s = Math.scalb(1.0, -80);
        assertEquals(1.0 + Math.ulp(1.0), StressDrift.fsum(new double[] {1.0, h, s}));
        assertEquals(1.0 + Math.ulp(1.0), StressDrift.fsum(new double[] {s, h, 1.0}));
        assertEquals(-1.0 - Math.ulp(1.0), StressDrift.fsum(new double[] {-1.0, -h, -s}));
        // exact halfway 1 + 2^-53 rounds to even (1.0); just below the tie rounds down.
        assertEquals(1.0, StressDrift.fsum(new double[] {1.0, h}));
        assertEquals(1.0, StressDrift.fsum(new double[] {1.0, h, -s}));
        assertEquals(6.0, StressDrift.fsum(new double[] {1, 2, 3}));
        assertEquals(0.0, StressDrift.fsum(new double[] {5.0, -5.0}));
    }

    // --- historicalShock ----------------------------------------------------------------------------

    private static final LocalDate D1 = LocalDate.of(2024, 1, 2);
    private static final LocalDate D2 = LocalDate.of(2024, 1, 3);
    private static final LocalDate D3 = LocalDate.of(2024, 1, 4);

    @Test
    void historicalShockValues() {
        double[][] y = {{1.0, 2.0, 3.0}, {1.5, 2.0, 3.25}, {2.0, 3.5, 5.0}};
        StressDrift.Shock s = StressDrift.historicalShock(List.of(D1, D2, D3), new double[] {1, 2, 5}, y, D1, D3);
        assertArrayEquals(new double[] {1.0, 2.0, 3.0}, s.startYields());
        assertArrayEquals(new double[] {2.0, 3.5, 5.0}, s.endYields());
        assertArrayEquals(new double[] {100.0, 150.0, 200.0}, s.shiftBp());
        assertEquals(150.0, s.levelBp());
        assertEquals(100.0, s.slopeBp());
        StressDrift.Shock t = StressDrift.historicalShock(List.of(D1, D2, D3), new double[] {1, 2, 5}, y, D2, D3);
        assertArrayEquals(new double[] {50.0, 150.0, 175.0}, t.shiftBp());
        assertEquals(125.0, t.levelBp());
        assertEquals(125.0, t.slopeBp());
        s.startYields()[0] = 99;
        assertEquals(1.0, y[0][0]);
    }

    @Test
    void historicalShockErrors() {
        double[] tn = {1, 2};
        double[][] y = {{1, 2}, {1, 2}};
        List<LocalDate> ds = List.of(D1, D2);
        err("E_INPUT", () -> StressDrift.historicalShock(List.of(), tn, new double[0][], D1, D2));
        err("E_INPUT", () -> StressDrift.historicalShock(ds, new double[0], new double[][] {{}, {}}, D1, D2));
        err("E_INPUT", () -> StressDrift.historicalShock(ds, tn, new double[][] {{1, 2}}, D1, D2));
        err("E_INPUT", () -> StressDrift.historicalShock(ds, tn, new double[][] {{1, 2}, {1}}, D1, D2));
        err("E_DATE_ORDER", "dates", () -> StressDrift.historicalShock(List.of(D2, D1), tn, y, D1, D2));
        err("E_DATE_ORDER", "dates", () -> StressDrift.historicalShock(List.of(D1, D1), tn, y, D1, D2));
        err("E_DOMAIN", "tenors", () -> StressDrift.historicalShock(ds, new double[] {0, 2}, y, D1, D2));
        err("E_DOMAIN", "tenors", () -> StressDrift.historicalShock(ds, new double[] {2, 2}, y, D1, D2));
        err("E_DOMAIN", "tenors", () -> StressDrift.historicalShock(ds, new double[] {2, 1}, y, D1, D2));
        err("E_DATE_ORDER", "end_date", () -> StressDrift.historicalShock(ds, tn, y, D2, D2));
        err("E_DATE_ORDER", "end_date", () -> StressDrift.historicalShock(ds, tn, y, D2, D1));
        err("E_DOMAIN", "start_date", () -> StressDrift.historicalShock(ds, tn, y, D1.minusDays(1), D2));
        err("E_DOMAIN", "end_date", () -> StressDrift.historicalShock(ds, tn, y, D1, D3));
    }

    // --- replay -------------------------------------------------------------------------------------

    @Test
    void replayFlatExtrapolationAndLinear() {
        double[] bt = {0.5, 1, 3, 5, 10};
        // shock 10bp at 1y, 50bp at 5y, scale 2: 0.5->20 (flat), 1->20, 3->60 (mid), 5->100, 10->100 (flat).
        StressDrift.Replay r = StressDrift.replay(bt, new double[] {1, 1, 1, 1, 1}, new double[] {1, 5},
                new double[] {10, 50}, 2.0, new double[] {1, 1, 1, 1, 1});
        assertArrayEquals(new double[] {20, 20, 60, 100, 100}, r.appliedBp());
        assertArrayEquals(new double[] {1.2, 1.2, 1.6, 2.0, 2.0}, r.shockedYields(), 1e-15);
        assertEquals(-300.0, r.pnl());
        // segment selection: t=2 at knot -> 10, t=3 in [2,4] -> 20, t=4 at end -> 30.
        StressDrift.Replay q = StressDrift.replay(new double[] {2, 3, 4}, new double[] {0, 0, 0},
                new double[] {1, 2, 4}, new double[] {0, 10, 30}, 1.0, null);
        assertArrayEquals(new double[] {10, 20, 30}, q.appliedBp());
        assertNull(q.pnl());
        StressDrift.Replay w = StressDrift.replay(new double[] {1.5}, new double[] {0}, new double[] {1, 2, 4},
                new double[] {0, 10, 30}, 1.0, new double[] {-2});
        assertArrayEquals(new double[] {5}, w.appliedBp());
        assertEquals(10.0, w.pnl());
    }

    @Test
    void replayErrors() {
        double[] t = {1, 2};
        err("E_INPUT", () -> StressDrift.replay(new double[0], new double[0], t, t, 1, null));
        err("E_INPUT", () -> StressDrift.replay(t, new double[] {1}, t, t, 1, null));
        err("E_INPUT", () -> StressDrift.replay(t, t, new double[0], new double[0], 1, null));
        err("E_INPUT", () -> StressDrift.replay(t, t, t, new double[] {1}, 1, null));
        err("E_INPUT", () -> StressDrift.replay(t, t, t, t, 1, new double[] {1}));
        err("E_DOMAIN", "base_tenors", () -> StressDrift.replay(new double[] {2, 1}, t, t, t, 1, null));
        err("E_DOMAIN", "shock_tenors", () -> StressDrift.replay(t, t, new double[] {-1, 1}, t, 1, null));
        assertThrows(QfError.class, () -> StressDrift.replay(t, t, t, t, Double.NaN, null));
        assertThrows(QfError.class, () -> StressDrift.replay(t, t, t, t, 1, new double[] {1, Double.NaN}));
    }

    // --- interpolation backtests --------------------------------------------------------------------

    @Test
    void interpLooLinear() {
        // leave 1: line (0,0)-(2,4) at 1 = 2, err 1; leave 2: (1,1)-(3,10) at 2 = 5.5, err 1.5.
        StressDrift.LooResult r = StressDrift.interpLoo(Interpolation.Method.LINEAR, new double[] {0, 1, 2, 3},
                new double[] {0, 1, 4, 10});
        assertArrayEquals(new double[] {1.0, 1.5}, r.errors(), 1e-15);
        assertEquals(1.5, r.maxAbsError(), 1e-15);
        assertEquals(Math.sqrt(1.625), r.rmse(), 1e-15);
        StressDrift.LooResult neg = StressDrift.interpLoo(Interpolation.Method.LINEAR, new double[] {0, 1, 2},
                new double[] {0, 3, 0});
        assertArrayEquals(new double[] {-3.0}, neg.errors(), 1e-15);
        assertEquals(3.0, neg.maxAbsError(), 1e-15);
        assertEquals(3.0, neg.rmse(), 1e-15);
        StressDrift.interpLoo(Interpolation.Method.CUBIC_NATURAL, new double[] {0, 1, 2, 3}, new double[] {0, 1, 2, 3});
        StressDrift.interpLoo(Interpolation.Method.CUBIC_NOT_A_KNOT, new double[] {0, 1, 2, 3, 4},
                new double[] {0, 1, 2, 3, 4});
    }

    @Test
    void interpLooErrors() {
        err("E_INPUT", () -> StressDrift.interpLoo(Interpolation.Method.LINEAR, new double[] {0, 1}, new double[] {0, 1}));
        err("E_INPUT", () -> StressDrift.interpLoo(Interpolation.Method.LINEAR, new double[] {0, 1, 2},
                new double[] {0, 1}));
        err("E_INPUT", () -> StressDrift.interpLoo(Interpolation.Method.CUBIC_NATURAL, new double[] {0, 1, 2},
                new double[] {0, 1, 2}));
        err("E_INPUT", () -> StressDrift.interpLoo(Interpolation.Method.TENSION, new double[] {0, 1, 2},
                new double[] {0, 1, 2}));
        err("E_INPUT", () -> StressDrift.interpLoo(Interpolation.Method.CUBIC_NOT_A_KNOT, new double[] {0, 1, 2, 3},
                new double[] {0, 1, 2, 3}));
        err("E_INPUT", () -> StressDrift.interpLoo(Interpolation.Method.LINEAR, new double[] {0, 1, 1},
                new double[] {0, 1, 2}));
    }

    @Test
    void surfaceHoldoutLinear() {
        // expiry 4: total variances 0.0025*4=0.01 and 0.01*4=0.04, midpoint 0.025, vol sqrt(0.025/4).
        StressDrift.SurfaceResult r = StressDrift.surfaceHoldout(Interpolation.Method.LINEAR, new double[] {4},
                new double[] {1, 2, 3}, new double[][] {{0.05, 0.3, 0.1}}, new long[] {1});
        double e = Math.sqrt(0.025 / 4) - 0.3;
        assertEquals(e, r.errors()[0][0], 1e-15);
        assertEquals(-e, r.maxAbsError(), 1e-15);
        assertEquals(-e, r.rmse(), 1e-15);
        // two expiries, strikes 1..5 hold 1 and 3; kept vols all 0.2 -> fitted 0.2 at the held strikes.
        StressDrift.SurfaceResult z = StressDrift.surfaceHoldout(Interpolation.Method.LINEAR, new double[] {1, 2},
                new double[] {1, 2, 3, 4, 5}, new double[][] {{0.2, 0.3, 0.2, 0.1, 0.2}, {0.2, 0.2, 0.2, 0.2, 0.2}},
                new long[] {1, 3});
        assertEquals(-0.1, z.errors()[0][0], 1e-12);
        assertEquals(0.1, z.errors()[0][1], 1e-12);
        assertEquals(0.0, z.errors()[1][0], 1e-12);
        assertEquals(0.1, z.maxAbsError(), 1e-12);
        assertEquals(Math.sqrt(0.02 / 4), z.rmse(), 1e-12);
    }

    @Test
    void surfaceHoldoutErrors() {
        Interpolation.Method l = Interpolation.Method.LINEAR;
        double[] k = {1, 2, 3};
        double[][] v = {{0.2, 0.2, 0.2}};
        double[] one = {1};
        err("E_INPUT", () -> StressDrift.surfaceHoldout(l, new double[0], k, new double[0][], new long[] {1}));
        err("E_INPUT", () -> StressDrift.surfaceHoldout(l, new double[] {1, 2}, k, v, new long[] {1}));
        err("E_INPUT", () -> StressDrift.surfaceHoldout(l, one, k, new double[][] {{0.2, 0.2}}, new long[] {1}));
        err("E_INPUT", () -> StressDrift.surfaceHoldout(l, one, new double[] {1, 3, 2}, v, new long[] {1}));
        err("E_INPUT", () -> StressDrift.surfaceHoldout(l, one, k, v, new long[0]));
        err("E_INPUT", () -> StressDrift.surfaceHoldout(l, one, k, v, new long[] {0}));
        err("E_INPUT", () -> StressDrift.surfaceHoldout(l, one, k, v, new long[] {2}));
        double[] k5 = {1, 2, 3, 4, 5};
        double[][] v5 = {{0.2, 0.2, 0.2, 0.2, 0.2}};
        err("E_INPUT", () -> StressDrift.surfaceHoldout(l, one, k5, v5, new long[] {2, 2}));
        err("E_INPUT", () -> StressDrift.surfaceHoldout(l, one, k5, v5, new long[] {3, 1}));
        err("E_INPUT", () -> StressDrift.surfaceHoldout(Interpolation.Method.CUBIC_NATURAL, one, k, v, new long[] {1}));
        StressDrift.surfaceHoldout(Interpolation.Method.CUBIC_NATURAL, one, new double[] {1, 2, 3, 4},
                new double[][] {{0.2, 0.2, 0.2, 0.2}}, new long[] {1});
        err("E_DOMAIN", () -> StressDrift.surfaceHoldout(l, new double[] {0}, k, v, new long[] {1}));
        err("E_DOMAIN", () -> StressDrift.surfaceHoldout(l, one, k, new double[][] {{0.2, 0.0, 0.2}}, new long[] {1}));
    }

    // --- CUSUM --------------------------------------------------------------------------------------

    @Test
    void cusumBranches() {
        // z=5: sp=4.5>4 alarm each step with restart.
        StressDrift.Alarms a = StressDrift.cusum(new double[] {5, 5, 5}, 0.5, 4.0, 0.0, 1.0, true);
        assertArrayEquals(new long[] {0, 1, 2}, a.alarms());
        assertArrayEquals(new long[] {1, 1, 1}, a.directions());
        assertEquals(0.0, a.sPlus());
        // no restart: stop at first alarm, sums kept.
        StressDrift.Alarms b = StressDrift.cusum(new double[] {5, 5, 5}, 0.5, 4.0, 0.0, 1.0, false);
        assertArrayEquals(new long[] {0}, b.alarms());
        assertEquals(4.5, b.sPlus());
        assertEquals(0.0, b.sMinus());
        // downward, standardised: z=(-1-1)/0.4=-5, sm=4.5.
        StressDrift.Alarms c = StressDrift.cusum(new double[] {-1}, 0.5, 4.0, 1.0, 0.4, false);
        assertArrayEquals(new long[] {-1}, c.directions());
        assertEquals(4.5, c.sMinus(), 1e-12);
        assertEquals(0.0, c.sPlus());
        // equality at h is not an alarm.
        StressDrift.Alarms d = StressDrift.cusum(new double[] {4.5}, 0.5, 4.0, 0.0, 1.0, true);
        assertEquals(0, d.alarms().length);
        assertEquals(4.0, d.sPlus());
        // accumulation: z=2.5 -> 2, 4, 6>5 alarm at index 2.
        StressDrift.Alarms e = StressDrift.cusum(new double[] {2.5, 2.5, 2.5}, 0.5, 5.0, 0.0, 1.0, true);
        assertArrayEquals(new long[] {2}, e.alarms());
        err("E_DOMAIN", () -> StressDrift.cusum(new double[] {1}, 0.0, 4, 0, 1, true));
        err("E_DOMAIN", () -> StressDrift.cusum(new double[] {1}, 0.5, 0, 0, 1, true));
        err("E_DOMAIN", () -> StressDrift.cusum(new double[] {1}, 0.5, 4, 0, 0, true));
        assertThrows(QfError.class, () -> StressDrift.cusum(new double[] {1}, 0.5, 4, Double.NaN, 1, true));
    }

    // --- Page-Hinkley -------------------------------------------------------------------------------

    @Test
    void pageHinkleyRestartAndDirections() {
        // up: t1 mean 5, up=5>4 alarm; restart -> t2 up 0, t3 up 5 alarm.
        double[] x = {0, 10, 0, 10};
        StressDrift.Alarms a = StressDrift.pageHinkley(x, 0.0, 4.0, "up", true);
        assertArrayEquals(new long[] {1, 3}, a.alarms());
        assertArrayEquals(new long[] {1, 1}, a.directions());
        assertArrayEquals(new long[] {1}, StressDrift.pageHinkley(x, 0.0, 4.0, "up", false).alarms());
        assertArrayEquals(new long[] {1, 3}, StressDrift.pageHinkley(x, 0.0, 4.0, "both", true).alarms());
        // delta 1: up = 5 - 1 = 4, not > 4.
        assertEquals(0, StressDrift.pageHinkley(new double[] {0, 10}, 1.0, 4.0, "up", true).alarms().length);
        double[] y = {0, -10, 0, -10};
        StressDrift.Alarms b = StressDrift.pageHinkley(y, 0.0, 4.0, "down", true);
        assertArrayEquals(new long[] {1, 3}, b.alarms());
        assertArrayEquals(new long[] {-1, -1}, b.directions());
        assertArrayEquals(new long[] {-1, -1}, StressDrift.pageHinkley(y, 0.0, 4.0, "both", true).directions());
        assertEquals(0, StressDrift.pageHinkley(y, 0.0, 4.0, "up", true).alarms().length);
        assertEquals(0, StressDrift.pageHinkley(x, 0.0, 4.0, "down", true).alarms().length);
        assertEquals(0.0, a.sPlus());
        err("E_INPUT", () -> StressDrift.pageHinkley(new double[0], 0, 1, "up", true));
        err("E_DOMAIN", () -> StressDrift.pageHinkley(x, -0.1, 1, "up", true));
        err("E_DOMAIN", () -> StressDrift.pageHinkley(x, 0, 0, "up", true));
        err("E_INPUT", () -> StressDrift.pageHinkley(x, 0, 1, "UP", true));
    }

    // --- PSI ----------------------------------------------------------------------------------------

    private static double[] oneToTen() {
        double[] r = new double[10];
        for (int i = 0; i < 10; i++) {
            r[i] = 10 - i;
        }
        return r;
    }

    @Test
    void psiEdgesAndFloor() {
        double[] ref = oneToTen();
        // bins 3, n 10: edges r[ceil(10/3)-1]=r[3]=4 and r[ceil(20/3)-1]=r[6]=7 -> shares .4 .3 .3.
        StressDrift.Psi p = StressDrift.psi(ref, ref, 3, 0.1);
        assertArrayEquals(new double[] {0.4, 0.3, 0.3}, p.referenceShares());
        assertEquals(0.0, p.psi());
        // edge value 4 is in bin 0 (v <= edge); 4.5 is in bin 1; above 7 is bin 2.
        double[] at = {4, 4, 4};
        StressDrift.Psi q = StressDrift.psi(ref, at, 3, 0.1);
        assertArrayEquals(new double[] {1.0, 1e-4, 1e-4}, q.testShares());
        assertArrayEquals(new double[] {1e-4, 1.0, 1e-4}, StressDrift.psi(ref, new double[] {4.5, 7, 5}, 3, 0.1).testShares());
        assertArrayEquals(new double[] {1e-4, 1e-4, 1.0}, StressDrift.psi(ref, new double[] {7.5, 100, 8}, 3, 0.1).testShares());
        double expect = (1.0 - 0.4) * Math.log(1.0 / 0.4) + 2 * (1e-4 - 0.3) * Math.log(1e-4 / 0.3);
        assertEquals(expect, q.psi(), 1e-12);
        assertTrue(q.alarm());
        assertFalse(StressDrift.psi(ref, at, 3, 1e6).alarm());
        // bins 2: edge r[4]=5.
        assertArrayEquals(new double[] {1.0, 1e-4}, StressDrift.psi(ref, new double[] {1, 2, 3, 4, 5}, 2, 0.1).testShares());
        assertArrayEquals(new double[] {0.5, 0.5}, StressDrift.psi(ref, new double[] {5, 6}, 2, 0.1).testShares());
        // bins 4, n 10: edges r[2]=3, r[4]=5, r[7]=8 -> shares .3 .2 .3 .2.
        assertArrayEquals(new double[] {0.3, 0.2, 0.3, 0.2}, StressDrift.psi(ref, ref, 4, 0.1).referenceShares());
        assertFalse(StressDrift.psi(ref, ref, 2, 1e-300).alarm());
    }

    @Test
    void psiErrors() {
        double[] ref = oneToTen();
        err("E_INPUT", () -> StressDrift.psi(ref, ref, 1, 0.1));
        err("E_INPUT", () -> StressDrift.psi(ref, ref, 11, 0.1));
        err("E_INPUT", () -> StressDrift.psi(ref, new double[] {1, 2}, 3, 0.1));
        err("E_INPUT", () -> StressDrift.psi(new double[] {1, 2}, ref, 3, 0.1));
        err("E_INPUT", () -> StressDrift.psi(ref, ref, Long.MAX_VALUE, 0.1));
        err("E_DOMAIN", () -> StressDrift.psi(ref, ref, 2, 0.0));
        StressDrift.psi(ref, ref, 10, 0.1);
        StressDrift.psi(new double[] {1, 2}, new double[] {1, 2}, 2, 0.1);
    }

    // --- KS -----------------------------------------------------------------------------------------

    @Test
    void ksHandCases() {
        // ties stepped together: D scaled 3 of 9; only diagonal paths survive |i-j|<1 -> none -> p 1.
        StressDrift.Ks t = StressDrift.ks(new double[] {1, 1, 2}, new double[] {1, 2, 2}, 0.05);
        assertEquals(1.0 / 3.0, t.statistic());
        assertEquals(1.0, t.pValue());
        assertFalse(t.reject());
        assertEquals(3L, StressDrift.ksDScaled(new double[] {1, 1, 2}, new double[] {2, 1, 2}));
        // a{1,2,4} b{3,5,6}: D scaled 6 -> 2/3; paths with |i-j|<=1: 8 of 20 -> p 0.6.
        StressDrift.Ks u = StressDrift.ks(new double[] {4, 2, 1}, new double[] {3, 5, 6}, 0.6);
        assertEquals(2.0 / 3.0, u.statistic());
        assertEquals(0.6, u.pValue());
        assertTrue(u.reject());
        assertFalse(StressDrift.ks(new double[] {4, 2, 1}, new double[] {3, 5, 6}, 0.59).reject());
        // unequal sizes n=1, m=2: d=2, one surviving path of 3 -> p 2/3.
        StressDrift.Ks v = StressDrift.ks(new double[] {1}, new double[] {2, 3}, 0.5);
        assertEquals(1.0, v.statistic());
        assertEquals(2.0 / 3.0, v.pValue());
        assertEquals(2.0 / 3.0, StressDrift.ks(new double[] {2, 3}, new double[] {1}, 0.5).pValue());
        StressDrift.Ks z = StressDrift.ks(new double[] {1, 2}, new double[] {1, 2}, 0.5);
        assertEquals(0.0, z.statistic());
        assertEquals(1.0, z.pValue());
        assertEquals(1.0, StressDrift.ksP(3, 3, 0));
        assertEquals(1.0, StressDrift.ksP(3, 3, -1));
        assertEquals(0.1, StressDrift.ksP(3, 3, 9));
        assertEquals(2.0 / 70.0, StressDrift.ksP(4, 4, 16));
        assertEquals(2.0 / 3.0, StressDrift.ksP(2, 1, 2));
        err("E_INPUT", () -> StressDrift.ks(new double[0], new double[] {1}, 0.5));
        err("E_INPUT", () -> StressDrift.ks(new double[] {1}, new double[0], 0.5));
        err("E_DOMAIN", () -> StressDrift.ks(new double[] {1}, new double[] {2}, 0.0));
        err("E_DOMAIN", () -> StressDrift.ks(new double[] {1}, new double[] {2}, 1.0));
    }

    @Test
    void nonFiniteInputsNameTheirField() {
        double n = Double.NaN;
        double[] t = {1, 2};
        double[] bad = {1, n};
        String d = "E_DOMAIN";
        List<LocalDate> ds = List.of(D1, D2);
        err(d, "tenors", () -> StressDrift.historicalShock(ds, bad, new double[][] {{1, 2}, {1, 2}}, D1, D2));
        err(d, "yields", () -> StressDrift.historicalShock(ds, t, new double[][] {{1, 2}, {1, n}}, D1, D2));
        err(d, "base_tenors", () -> StressDrift.replay(bad, t, t, t, 1, null));
        err(d, "base_yields", () -> StressDrift.replay(t, bad, t, t, 1, null));
        err(d, "shock_tenors", () -> StressDrift.replay(t, t, bad, t, 1, null));
        err(d, "shock_bp", () -> StressDrift.replay(t, t, t, bad, 1, null));
        err(d, "scale", () -> StressDrift.replay(t, t, t, t, n, null));
        err(d, "dv01", () -> StressDrift.replay(t, t, t, t, 1, bad));
        Interpolation.Method l = Interpolation.Method.LINEAR;
        err(d, "x", () -> StressDrift.interpLoo(l, new double[] {0, 1, n}, new double[] {0, 1, 2}));
        err(d, "y", () -> StressDrift.interpLoo(l, new double[] {0, 1, 2}, new double[] {0, 1, n}));
        double[] k = {1, 2, 3};
        double[][] v = {{0.2, 0.2, 0.2}};
        err(d, "expiries", () -> StressDrift.surfaceHoldout(l, new double[] {n}, k, v, new long[] {1}));
        err(d, "strikes", () -> StressDrift.surfaceHoldout(l, new double[] {1}, new double[] {1, 2, n}, v, new long[] {1}));
        err(d, "vols", () -> StressDrift.surfaceHoldout(l, new double[] {1}, k, new double[][] {{0.2, n, 0.2}},
                new long[] {1}));
        double[] one = {1};
        err(d, "x", () -> StressDrift.cusum(new double[] {n}, 0.5, 4, 0, 1, true));
        err(d, "k", () -> StressDrift.cusum(one, n, 4, 0, 1, true));
        err(d, "h", () -> StressDrift.cusum(one, 0.5, n, 0, 1, true));
        err(d, "mu0", () -> StressDrift.cusum(one, 0.5, 4, n, 1, true));
        err(d, "sigma", () -> StressDrift.cusum(one, 0.5, 4, 0, n, true));
        err(d, "x", () -> StressDrift.pageHinkley(new double[] {n}, 0, 1, "up", true));
        err(d, "delta", () -> StressDrift.pageHinkley(one, n, 1, "up", true));
        err(d, "lambda", () -> StressDrift.pageHinkley(one, 0, n, "up", true));
        double[] ref = oneToTen();
        double[] refBad = ref.clone();
        refBad[0] = n;
        err(d, "reference", () -> StressDrift.psi(refBad, ref, 2, 0.1));
        err(d, "test", () -> StressDrift.psi(ref, refBad, 2, 0.1));
        err(d, "threshold", () -> StressDrift.psi(ref, ref, 2, n));
        err(d, "a", () -> StressDrift.ks(new double[] {n}, one, 0.5));
        err(d, "b", () -> StressDrift.ks(one, new double[] {n}, 0.5));
        err(d, "level", () -> StressDrift.ks(one, one, n));
    }

    @Test
    void boundaryCases() {
        // CUSUM downward equality at h: z=-4.5, sm=4 not > 4.
        assertEquals(0, StressDrift.cusum(new double[] {-4.5}, 0.5, 4.0, 0.0, 1.0, true).alarms().length);
        // PH up-down equality: x {0,-8}: mean -4, dn = 4, not > 4 for lambda 4.
        assertEquals(0, StressDrift.pageHinkley(new double[] {0, -8}, 0.0, 4.0, "down", true).alarms().length);
        // replay at the first shock knot and between: t=1 exactly (flat branch) and 1.0 left boundary.
        StressDrift.Replay r = StressDrift.replay(new double[] {1, 4}, new double[] {0, 0}, new double[] {1, 2, 4},
                new double[] {6, 10, 30}, 1.0, null);
        assertArrayEquals(new double[] {6, 30}, r.appliedBp());
        // historical shock where end is the last date and start the first of four.
        LocalDate d4 = LocalDate.of(2024, 1, 5);
        StressDrift.Shock s = StressDrift.historicalShock(List.of(D1, D2, D3, d4), new double[] {1},
                new double[][] {{1}, {2}, {3}, {5}}, D1, d4);
        assertArrayEquals(new double[] {400}, s.shiftBp());
        // ks: d just above the max reachable |im-jn| -> every path counts, p 0.
        assertEquals(0.0, StressDrift.ksP(2, 2, 5));
        assertEquals(1.0, StressDrift.ksP(2, 2, 1));
        // n=1,m=1: d=1 -> no path keeps |i-j|<1 after the first step -> p 1; d=2 -> p 0.
        assertEquals(1.0, StressDrift.ksP(1, 1, 1));
        assertEquals(0.0, StressDrift.ksP(1, 1, 2));
        // surface: holdout index m-2 is allowed.
        StressDrift.surfaceHoldout(Interpolation.Method.LINEAR, new double[] {1}, new double[] {1, 2, 3, 4},
                new double[][] {{0.2, 0.2, 0.2, 0.2}}, new long[] {2});
        // loo for LINEAR with n=3 uses 2 knots: allowed (minKnots 2); MONOTONE_PCHIP too.
        assertEquals(1, StressDrift.interpLoo(Interpolation.Method.MONOTONE_PCHIP, new double[] {0, 1, 2},
                new double[] {0, 1, 2}).errors().length);
        // psi with n not divisible: bins 3, n 4: edges r[ceil(4/3)-1]=r[1], r[ceil(8/3)-1]=r[2].
        assertArrayEquals(new double[] {0.5, 0.25, 0.25},
                StressDrift.psi(new double[] {1, 2, 3, 4}, new double[] {1, 2, 3, 4}, 3, 0.1).referenceShares());
    }

    @Test
    void ratioRounding() {
        BigInteger one = BigInteger.ONE;
        BigInteger three = BigInteger.valueOf(3);
        assertEquals(0.0, StressDrift.ratio(BigInteger.ZERO, BigInteger.TEN));
        assertEquals(1.0 / 3.0, StressDrift.ratio(one, three));
        assertEquals(2.0 / 3.0, StressDrift.ratio(BigInteger.TWO, three));
        assertEquals(2.5, StressDrift.ratio(BigInteger.TEN, BigInteger.valueOf(4)));
        assertEquals(1.0, StressDrift.ratio(BigInteger.valueOf(7), BigInteger.valueOf(7)));
        assertEquals(0x1p60 / 3.0, StressDrift.ratio(one.shiftLeft(60), three));
        // integer ties: 2^53+1 -> 2^53 (even), 2^53+3 -> 2^53+4.
        assertEquals(0x1p53, StressDrift.ratio(one.shiftLeft(53).add(one), one));
        assertEquals(0x1p53 + 4, StressDrift.ratio(one.shiftLeft(53).add(three), one));
        // just above the tie 2^53+1 (sticky remainder): rounds up to 2^53+2.
        assertEquals(0x1p53 + 2, StressDrift.ratio(one.shiftLeft(53).add(one).multiply(three).add(one), three));
        // subnormals: 2^-1074 exact, 1.5*2^-1074 tie -> 2*2^-1074, 0.5*2^-1074 tie -> 0, far below -> 0.
        assertEquals(Double.MIN_VALUE, StressDrift.ratio(one, one.shiftLeft(1074)));
        assertEquals(2 * Double.MIN_VALUE, StressDrift.ratio(three, one.shiftLeft(1075)));
        assertEquals(0.0, StressDrift.ratio(one, one.shiftLeft(1075)));
        assertEquals(Double.MIN_VALUE, StressDrift.ratio(three, one.shiftLeft(1076)));
        assertEquals(0.0, StressDrift.ratio(one, one.shiftLeft(1100)));
        assertEquals(Double.MIN_NORMAL, StressDrift.ratio(one, one.shiftLeft(1022)));
        assertEquals(0.1, StressDrift.ratio(one, BigInteger.TEN));
        assertEquals(0.9, StressDrift.ratio(BigInteger.valueOf(9), BigInteger.TEN));
    }
}
