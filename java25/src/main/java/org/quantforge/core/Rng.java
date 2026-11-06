package org.quantforge.core;

/** SplitMix64 seeding, xoshiro256** and AS 241 normals (rng.md). One instance per run. */
public final class Rng {
    private static final long[] JUMP = {
        0x180EC6D33CFD0ABAL, 0xD5A61266F0C9392CL, 0xA9582618E03FC9AAL, 0x39ABDC4529B1661CL};

    private final long[] s;

    private Rng(long[] state) {
        s = state;
    }

    public static Rng fromState(long[] state) {
        return new Rng(state.clone());
    }

    public static Rng seeded(long seed, int stream) {
        long[] w = new long[4];
        long state = seed;
        for (int k = 0; k < 4; k++) {
            state += 0x9E3779B97F4A7C15L;
            long z = state;
            z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
            z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
            w[k] = z ^ (z >>> 31);
        }
        Rng r = new Rng(w);
        for (int k = 0; k < stream; k++) {
            r.jump();
        }
        return r;
    }

    public long nextLong() {
        long result = Long.rotateLeft(s[1] * 5, 7) * 9;
        long t = s[1] << 17;
        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];
        s[2] ^= t;
        s[3] = Long.rotateLeft(s[3], 45);
        return result;
    }

    private void jump() {
        long[] n = new long[4];
        for (long w : JUMP) {
            for (int b = 0; b < 64; b++) {
                if ((w >>> b & 1L) != 0) {
                    for (int k = 0; k < 4; k++) {
                        n[k] ^= s[k];
                    }
                }
                nextLong();
            }
        }
        System.arraycopy(n, 0, s, 0, 4);
    }

    public double nextUniform() {
        return ((nextLong() >>> 12) + 0.5) * 0x1p-52;
    }

    public double nextNormal() {
        return ppnd16(nextUniform());
    }

    private static final double[] A = {3.387132872796366608, 133.14166789178437745, 1971.5909503065514427,
        13731.693765509461125, 45921.953931549871457, 67265.770927008700853, 33430.575583588128105,
        2509.0809287301226727};
    private static final double[] B = {1, 42.313330701600911252, 687.18700749205790830, 5394.1960214247511077,
        21213.794301586595867, 39307.895800092710610, 28729.085735721942674, 5226.4952788528545610};
    private static final double[] C = {1.42343711074968357734, 4.63033784615654529590, 5.76949722146069140550,
        3.64784832476320460504, 1.27045825245236838258, 0.241780725177450611770, 0.0227238449892691845833,
        0.000774545014278341407640};
    private static final double[] D = {1, 2.05319162663775882187, 1.67638483018380384940, 0.689767334985100004550,
        0.148103976427480074590, 0.0151986665636164571966, 0.000547593808499534494600, 1.05075007164441684324e-9};
    private static final double[] E = {6.65790464350110377720, 5.46378491116411436990, 1.78482653991729133580,
        0.296560571828504891230, 0.0265321895265761230930, 0.00124266094738807843860, 0.0000271155556874348757815,
        2.01033439929228813265e-7};
    private static final double[] F = {1, 0.599832206555887937690, 0.136929880922735805310, 0.0148753612908506148525,
        0.000786869131145613259100, 0.0000184631831751005468180, 1.42151175831644588870e-7, 2.04426310338993978564e-15};

    private static double horner(double[] c, double x) {
        double v = c[c.length - 1];
        for (int k = c.length - 2; k >= 0; k--) {
            v = v * x + c[k];
        }
        return v;
    }

    /** Wichura's AS 241 inverse normal. {@code p} must lie in (0, 1). */
    public static double ppnd16(double p) {
        double q = p - 0.5;
        if (Math.abs(q) <= 0.425) {
            double r = 0.180625 - q * q;
            return q * horner(A, r) / horner(B, r);
        }
        double r = Math.sqrt(-Math.log(q < 0 ? p : 1 - p));
        double v;
        if (r <= 5) {
            r -= 1.6;
            v = horner(C, r) / horner(D, r);
        } else {
            r -= 5;
            v = horner(E, r) / horner(F, r);
        }
        return q < 0 ? -v : v;
    }
}
