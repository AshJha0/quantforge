package org.quantforge.research;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Interpolation;
import org.quantforge.core.QfError;

/** Stage J wave 3 unit tests (rulings J-W3-2 to J-W3-13), own data; mirrors the Rust and C++ [w3] tests. */
class StressDriftTest {

    @Test
    void cusumHandCaseAndRestart() {
        StressDrift.Alarms a = StressDrift.cusum(new double[] {0.0, 3.0, 3.0}, 0.5, 4.0, 0.0, 1.0, true);
        assertArrayEquals(new long[] {2}, a.alarms());
        assertArrayEquals(new long[] {1}, a.directions());
        assertEquals(0.0, a.sPlus());
        assertThrows(QfError.class, () -> StressDrift.cusum(new double[0], 0.5, 4.0, 0.0, 1.0, true));
    }

    @Test
    void pageHinkleyConstantNeverAlarmsAndStepAlarms() {
        double[] flat = new double[50];
        Arrays.fill(flat, 1.0);
        assertEquals(0, StressDrift.pageHinkley(flat, 0.0, 1.0, "both", true).alarms().length);
        double[] step = new double[20];
        Arrays.fill(step, 10, 20, 3.0);
        // Same alarm index as python/quantforge_core/drift.py page_hinkley.
        assertArrayEquals(new long[] {11}, StressDrift.pageHinkley(step, 0.0, 5.0, "up", true).alarms());
        assertThrows(QfError.class, () -> StressDrift.pageHinkley(step, 0.0, 5.0, "sideways", true));
    }

    @Test
    void psiIdenticalSamplesIsZero() {
        double[] x = new double[100];
        for (int i = 0; i < 100; i++) {
            x[i] = i;
        }
        StressDrift.Psi p = StressDrift.psi(x, x, 10, 0.25);
        assertEquals(0.0, p.psi());
        assertFalse(p.alarm());
    }

    @Test
    void ksSeparatedSamples() {
        StressDrift.Ks k = StressDrift.ks(new double[] {1, 2, 3, 4}, new double[] {5, 6, 7, 8}, 0.05);
        assertEquals(1.0, k.statistic());
        assertEquals(2.0 / 70.0, k.pValue(), 1e-15);
        assertTrue(k.reject());
    }

    @Test
    void ksExactBigIntegerPathBeyond128Bits() {
        // C(160, 80) is about 9.2e46, past 2^128: only the BigInteger count gets this right.
        double[] a = new double[80];
        double[] b = new double[80];
        for (int i = 0; i < 80; i++) {
            a[i] = i;
            b[i] = 100 + i;
        }
        StressDrift.Ks k = StressDrift.ks(a, b, 0.05);
        assertEquals(1.0, k.statistic());
        assertEquals(2.172847266293351e-47, k.pValue()); // float(Fraction(2, comb(160, 80)))
        // Overlapping samples, reference from python/quantforge_core/drift.py ks.
        double[] c = new double[90];
        double[] d = new double[85];
        for (int i = 0; i < 90; i++) {
            c[i] = i * 0.37 % 5;
        }
        for (int i = 0; i < 85; i++) {
            d[i] = (i * 0.53) % 5.2 + 0.6;
        }
        StressDrift.Ks k2 = StressDrift.ks(c, d, 0.05);
        assertEquals(0.15555555555555556, k2.statistic());
        assertEquals(0.211209319744788, k2.pValue(), 1e-15);
        assertFalse(k2.reject());
    }

    @Test
    void ksPathCountIsSymmetricAndMonotone() {
        for (int[] nm : new int[][] {{4, 4}, {7, 5}, {12, 9}}) {
            int n = nm[0];
            int m = nm[1];
            double prev = 1.0;
            for (long d = 1; d <= (long) n * m; d++) {
                double p = StressDrift.ksP(n, m, d);
                assertEquals(p, StressDrift.ksP(m, n, d), 1e-15);
                assertTrue(p <= prev + 1e-15 && p >= 0.0);
                prev = p;
            }
        }
    }

    @Test
    void fsumIsCorrectlyRounded() {
        assertEquals(1.0, StressDrift.fsum(new double[] {1e100, 1.0, -1e100}));
        assertEquals(0.30000000000000004, StressDrift.fsum(new double[] {0.1, 0.1, 0.1}));
    }

    @Test
    void replayFlatOutsideTheShockTenors() {
        StressDrift.Replay r = StressDrift.replay(new double[] {0.5, 1.0, 40.0}, new double[] {1, 1, 1},
                new double[] {1.0, 10.0}, new double[] {10.0, 20.0}, 1.0, new double[] {1, 1, 1});
        assertArrayEquals(new double[] {10.0, 10.0, 20.0}, r.appliedBp());
        assertEquals(-40.0, r.pnl());
        assertEquals(null, StressDrift.replay(new double[] {1.0}, new double[] {1}, new double[] {1.0},
                new double[] {5.0}, 1.0, null).pnl());
    }

    @Test
    void historicalShockAndMissingDate() {
        List<LocalDate> dates = List.of(LocalDate.of(2020, 1, 2), LocalDate.of(2020, 1, 3));
        double[][] y = {{1.0, 2.0}, {1.5, 1.75}};
        StressDrift.Shock s = StressDrift.historicalShock(dates, new double[] {2, 10}, y, dates.get(0), dates.get(1));
        assertArrayEquals(new double[] {50.0, -25.0}, s.shiftBp());
        assertThrows(QfError.class, () -> StressDrift.historicalShock(dates, new double[] {2, 10}, y,
                LocalDate.of(2020, 1, 1), dates.get(1)));
    }

    @Test
    void interpLooLinearIsExactOnALine() {
        double[] x = {0, 1, 2, 3, 4};
        double[] y = {1, 3, 5, 7, 9};
        StressDrift.LooResult r = StressDrift.interpLoo(Interpolation.Method.LINEAR, x, y);
        assertEquals(3, r.errors().length);
        assertEquals(0.0, r.maxAbsError(), 1e-15);
        assertThrows(QfError.class, () -> StressDrift.interpLoo(Interpolation.Method.LINEAR,
                new double[] {0, 2, 1}, new double[] {0, 0, 0}));
    }

    @Test
    void ksRatioIsCorrectlyRoundedAtHalfway() {
        java.math.BigInteger two = java.math.BigInteger.TWO;
        java.math.BigInteger mid = two.pow(53).add(java.math.BigInteger.ONE); // (2^53 + 1) / 2^54: a tie
        java.math.BigInteger den = two.pow(254);
        java.math.BigInteger tie = mid.shiftLeft(200);
        double up = Math.nextUp(0.5);
        assertEquals(0.5, StressDrift.ratio(tie, den)); // tie to even
        assertEquals(up, StressDrift.ratio(tie.add(java.math.BigInteger.ONE), den)); // 2^-254 above the tie
        assertEquals(0.5, StressDrift.ratio(tie.subtract(java.math.BigInteger.ONE), den));
        assertEquals(1.0 / 3.0, StressDrift.ratio(java.math.BigInteger.ONE, java.math.BigInteger.valueOf(3)));
        assertEquals(1.0, StressDrift.ratio(den, den));
        assertEquals(Double.MIN_VALUE, StressDrift.ratio(java.math.BigInteger.ONE, two.pow(1074)));
        assertEquals(0.0, StressDrift.ratio(java.math.BigInteger.ONE, two.pow(1075))); // tie to even (zero)
        assertEquals(Double.MIN_VALUE, StressDrift.ratio(java.math.BigInteger.ONE, two.pow(1075).subtract(java.math.BigInteger.ONE)));
    }
}
