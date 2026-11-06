package org.quantforge.core;

/**
 * Standard normal density and distribution function. The tail works directly in x, with the Mills-ratio
 * continued fraction and a split square, because going through x/sqrt(2) and a rounded x^2 costs about
 * 1e-13 relative at x = -37, over the spec's limit of 1e-14.
 */
public final class Normal {
    private Normal() {}

    private static final double INV_SQRT_2PI = 0.3989422804014326779399460599343819;

    public static double pdf(double x) {
        double a = Math.abs(x);
        if (a > 40.0) {
            return 0.0;
        }
        double hi = Math.rint(a * 16.0) / 16.0; // hi^2 is exact.
        double del = (a - hi) * (a + hi);
        return INV_SQRT_2PI * Math.exp(-hi * hi / 2.0) * Math.exp(-del / 2.0);
    }

    /** Upper tail for a >= 2: n(a) times the Mills ratio. */
    private static double tail(double a) {
        double f = a;
        for (int k = 300; k >= 1; k--) {
            f = a + k / f;
        }
        return pdf(a) / f;
    }

    /** x + x^3/3 + x^5/(3 5) + ..., all terms of one sign, so that N(x) = 1/2 + n(x) times it. */
    private static double series(double x) {
        double term = x;
        double sum = x;
        for (int k = 3; Math.abs(term) > 1e-18 * Math.abs(sum); k += 2) {
            term *= x * x / k;
            sum += term;
        }
        return sum;
    }

    public static double cdf(double x) {
        double a = Math.abs(x);
        if (a < 2.0) {
            return x == 0.0 ? 0.5 : 0.5 + pdf(x) * series(x);
        }
        if (a > 40.0) {
            return x < 0 ? 0.0 : 1.0;
        }
        return x < 0 ? tail(a) : 1.0 - tail(a);
    }
}
