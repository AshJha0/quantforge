package org.quantforge.micro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

/**
 * The numpy port against values numpy 2.4.6 printed (2026-11-18): the first draws of three seeds in the order the
 * recovery tests interleave them, two PTRS Poisson draws after 3,000 rounds, and a 200,000-draw ziggurat checksum.
 * A wider comparison (36,012 draws over the three seeds) matched exactly before these were fixed.
 */
class NumpyRngTest {
    @Test
    void firstDrawsMatchNumpy() {
        Object[][] want = {
            {20261119L, 1684628720167899607L, 0.29071362979956594, -1L, 58L, -0.06724342672535288, 2.7156780461168064, 9010L, 9077L},
            {70000L, 6024274701318062869L, 0.4008755151155149, 1L, 93L, 0.01077855715010661, 6.522768631588426, 8887L, 9109L},
            {70123L, 7416423396052956773L, 0.11062102713738753, -1L, 39L, 0.017782774812657554, 0.7215412971042601, 8924L, 9023L},
        };
        for (Object[] w : want) {
            NumpyRng r = new NumpyRng((Long) w[0]);
            assertEquals(w[1], r.nextLong());
            assertEquals(w[2], r.random());
            long s = r.choice(new long[] {-1, 1});
            long q = r.integers(1, 101);
            double n = r.normal(0, 0.05);
            double e = r.exponential(2.0);
            assertEquals(w[3], s);
            assertEquals(w[4], q);
            assertEquals(w[5], n);
            assertEquals(w[6], e);
            for (int i = 1; i < 3000; i++) {
                r.choice(new long[] {-1, 1});
                r.integers(1, 101);
                r.normal(0, 0.05);
                r.exponential(2.0);
            }
            assertEquals(w[7], r.poisson(9000.0));
            assertEquals(w[8], r.poisson(9000.0));
        }
    }

    @Test
    void zigguratChecksum() {
        NumpyRng r = new NumpyRng(70000);
        double[] v = new double[200_000];
        for (int i = 0; i < 100_000; i++) {
            v[i] = r.standardNormal();
        }
        for (int i = 100_000; i < 200_000; i++) {
            v[i] = r.standardExponential();
        }
        assertEquals(100216.18527592497, org.quantforge.research.StressDrift.fsum(v)); // math.fsum in numpy's run
        assertEquals(1.4622581364761265, v[199_999]);
    }

    @Test
    void guards() {
        assertThrows(IllegalArgumentException.class, () -> new NumpyRng(-1));
        assertThrows(IllegalArgumentException.class, () -> new NumpyRng(1L << 32));
        assertThrows(IllegalArgumentException.class, () -> new NumpyRng(1).poisson(5.0));
        assertEquals(7L, new NumpyRng(1).integers(7, 8));
        assertEquals(0.0, NumpyRng.loggam(1.0));
        assertEquals(0.0, NumpyRng.loggam(2.0));
        assertEquals(Math.log(6.0), NumpyRng.loggam(4.0), 1e-14);
    }
}
