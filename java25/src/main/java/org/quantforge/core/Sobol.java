package org.quantforge.core;

/** Unscrambled Sobol points by Gray code (sobol.md). Serves index 1 first; the origin is never returned. */
public final class Sobol {
    public static final int MAX_DIMENSIONS = 64;

    private final int[][] v; // v[d][k], k = 1..32
    private final int[] x;
    private long index;

    /** Positions the sequence so that the next point served has index {@code skip + 1}. */
    public Sobol(int dimensions, long skip) {
        v = new int[dimensions][];
        for (int d = 0; d < dimensions; d++) {
            v[d] = directions(d);
        }
        x = new int[dimensions];
        index = skip;
        long gray = skip ^ (skip >>> 1); // State at index i is the XOR of v[c] over the set bits of gray(i).
        for (int c = 1; c <= 32; c++) {
            if ((gray >>> (c - 1) & 1L) != 0) {
                for (int d = 0; d < dimensions; d++) {
                    x[d] ^= v[d][c];
                }
            }
        }
    }

    private static int[] directions(int d) {
        int[] w = new int[33];
        if (d == 0) {
            for (int k = 1; k <= 32; k++) {
                w[k] = 1 << (32 - k);
            }
            return w;
        }
        int s = SobolData.S[d];
        int a = SobolData.A[d];
        int[] m = SobolData.M[d];
        for (int k = 1; k <= Math.min(s, 32); k++) {
            w[k] = m[k - 1] << (32 - k);
        }
        for (int k = s + 1; k <= 32; k++) {
            w[k] = w[k - s] ^ (w[k - s] >>> s);
            for (int j = 1; j <= s - 1; j++) {
                if ((a >>> (s - 1 - j) & 1) != 0) {
                    w[k] ^= w[k - j];
                }
            }
        }
        return w;
    }

    /** Writes the next point into {@code out}. */
    public void next(double[] out) {
        int c = Long.numberOfTrailingZeros(~index) + 1; // Lowest zero bit of index, from 1.
        for (int d = 0; d < x.length; d++) {
            x[d] ^= v[d][c];
            out[d] = (x[d] & 0xFFFFFFFFL) * 0x1p-32;
        }
        index++;
    }
}
