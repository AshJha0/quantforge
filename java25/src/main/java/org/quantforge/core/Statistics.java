package org.quantforge.core;

import java.util.Arrays;

/** Moments, quantiles, covariance and least squares (statistics-and-time-series.md). */
public final class Statistics {
    private Statistics() {}

    /** {@code skewness} and {@code excessKurtosis} are null at zero variance. */
    public record Summary(int count, double mean, double variance, double stdev, Double skewness,
                          Double excessKurtosis, double min, double max) {}

    /** {@code correlation} is null when either variance is zero. */
    public record Covariance(double covariance, Double correlation) {}

    /** {@code rSquared} is null when y has zero variance. */
    public record Ols(double alpha, double beta, Double rSquared, double seAlpha, double seBeta, double sse) {}

    static boolean constant(double[] x) {
        for (double v : x) {
            if (v != x[0]) {
                return false;
            }
        }
        return true;
    }

    /** Mean, exact for a constant series so that its deviations are exactly zero. */
    public static double mean(double[] x) {
        if (constant(x)) {
            return x[0];
        }
        double s = 0.0;
        for (double v : x) {
            s += v;
        }
        return s / x.length;
    }

    /**
     * Deviations from the mean, by the spec's shift: y_i = x_i - x_0, which is exact for nearby values,
     * then d_i = y_i - mean(y).
     */
    static double[] centered(double[] x) {
        double my = shiftMean(x);
        double[] d = new double[x.length];
        for (int i = 0; i < x.length; i++) {
            d[i] = (x[i] - x[0]) - my;
        }
        return d;
    }

    private static double shiftMean(double[] x) {
        double s = 0.0;
        for (double v : x) {
            s += v - x[0];
        }
        return s / x.length;
    }

    /** The mean reported by the moment operations: x_0 + mean(y). */
    static double shiftedMean(double[] x) {
        return x[0] + shiftMean(x);
    }

    static double sumSquares(double[] d) {
        double s = 0.0;
        for (double v : d) {
            s += v * v;
        }
        return s;
    }

    private static double sumProducts(double[] a, double[] b) {
        double s = 0.0;
        for (int i = 0; i < a.length; i++) {
            s += a[i] * b[i];
        }
        return s;
    }

    public static Summary summary(double[] x) {
        int n = x.length;
        if (n < 2) {
            throw new QfError("E_INPUT", "need at least 2 values", "x");
        }
        double m = shiftedMean(x);
        double s2 = 0.0;
        double s3 = 0.0;
        double s4 = 0.0;
        double min = x[0];
        double max = x[0];
        double[] dev = centered(x);
        for (int i = 0; i < n; i++) {
            double d = dev[i];
            s2 += d * d;
            s3 += d * d * d;
            s4 += d * d * d * d;
            min = Math.min(min, x[i]);
            max = Math.max(max, x[i]);
        }
        double variance = s2 / (n - 1);
        Double skew = null;
        Double kurt = null;
        if (!constant(x)) {
            double m2 = s2 / n;
            skew = (s3 / n) / Math.pow(m2, 1.5);
            kurt = (s4 / n) / (m2 * m2) - 3.0;
        }
        return new Summary(n, m, variance, Math.sqrt(variance), skew, kurt, min, max);
    }

    public static double[] quantile(double[] x, double[] p) {
        if (x.length < 1) {
            throw new QfError("E_INPUT", "need at least 1 value", "x");
        }
        double[] s = x.clone();
        Arrays.sort(s);
        double[] out = new double[p.length];
        for (int i = 0; i < p.length; i++) {
            if (!(p[i] >= 0.0 && p[i] <= 1.0)) {
                throw new QfError("E_DOMAIN", "p outside [0, 1]", "p");
            }
            double h = (s.length - 1) * p[i];
            int k = (int) Math.floor(h);
            out[i] = k >= s.length - 1 ? s[s.length - 1] : s[k] + (h - k) * (s[k + 1] - s[k]);
        }
        return out;
    }

    public static Covariance covariance(double[] x, double[] y) {
        if (x.length != y.length || x.length < 2) {
            throw new QfError("E_INPUT", "need equal lengths of at least 2");
        }
        double[] dx = centered(x);
        double[] dy = centered(y);
        double sxy = sumProducts(dx, dy);
        double sxx = sumSquares(dx);
        double syy = sumSquares(dy);
        Double corr = constant(x) || constant(y) ? null : sxy / Math.sqrt(sxx * syy);
        return new Covariance(sxy / (x.length - 1), corr);
    }

    /** Fits y = alpha + beta x. {@code dof} is the residual degrees of freedom. */
    static Ols fit(double[] x, double[] y, int dof) {
        int n = x.length;
        double mx = shiftedMean(x);
        double my = shiftedMean(y);
        double[] dx = centered(x);
        double[] dy = centered(y);
        double sxx = sumSquares(dx);
        if (constant(x)) {
            throw new QfError("E_SINGULAR", "zero variance in x", "x");
        }
        double syy = sumSquares(dy);
        double beta = sumProducts(dx, dy) / sxx;
        double alpha = my - beta * mx;
        double sse = 0.0;
        for (int i = 0; i < n; i++) {
            double e = dy[i] - beta * dx[i];
            sse += e * e;
        }
        double s2 = sse / dof;
        double seBeta = Math.sqrt(s2 / sxx);
        double seAlpha = Math.sqrt(s2 * (1.0 / n + mx * mx / sxx));
        Double r2 = constant(y) ? null : 1.0 - sse / syy;
        return new Ols(alpha, beta, r2, seAlpha, seBeta, sse);
    }

    public static Ols ols(double[] x, double[] y) {
        if (x.length != y.length || x.length < 3) {
            throw new QfError("E_INPUT", "need equal lengths of at least 3");
        }
        return fit(x, y, x.length - 2);
    }
}
