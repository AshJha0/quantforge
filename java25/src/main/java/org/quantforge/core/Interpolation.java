package org.quantforge.core;

import java.util.Arrays;

/** One-dimensional interpolation (interpolation.md, operation core.interp.evaluate). */
public final class Interpolation {
    private Interpolation() {}

    public enum Method {
        LINEAR(2), LOG_LINEAR(2), CUBIC_NATURAL(3), CUBIC_CLAMPED(2), CUBIC_NOT_A_KNOT(4), MONOTONE_PCHIP(2), TENSION(3);

        final int minKnots;

        Method(int minKnots) {
            this.minKnots = minKnots;
        }

        public boolean hasDerivatives() {
            return this != LINEAR && this != LOG_LINEAR;
        }
    }

    /** Method parameters; each is read only by the method that needs it. */
    public record Params(double slopeStart, double slopeEnd, double tension) {}

    /** {@code derivatives} is null for methods that do not report them. */
    public record Result(double[] values, double[] derivatives) {}

    static void checkKnots(double[] x, double[] y, int min) {
        if (x.length != y.length || x.length < min) {
            throw new QfError("E_INPUT", "lengths differ or too few knots");
        }
        for (int i = 1; i < x.length; i++) {
            if (!(x[i] > x[i - 1])) {
                throw new QfError("E_INPUT", "knots not strictly increasing", "x");
            }
        }
    }

    public static Result evaluate(Method method, double[] x, double[] y, double[] at, Params params) {
        checkKnots(x, y, method.minKnots);
        Method m = method;
        double p = params.tension();
        if (m == Method.LOG_LINEAR) {
            for (double v : y) {
                if (v <= 0.0) {
                    throw new QfError("E_DOMAIN", "log_linear needs positive y", "y");
                }
            }
        }
        if (m == Method.TENSION) {
            if (p < 0.0) {
                throw new QfError("E_DOMAIN", "tension is negative", "tension");
            }
            if (p == 0.0) {
                m = Method.CUBIC_NATURAL;
            } else {
                for (int i = 0; i + 1 < x.length; i++) {
                    double ph = p * (x[i + 1] - x[i]);
                    if (ph < 0.01 || ph > 500.0) {
                        throw new QfError("E_DOMAIN", "p h outside [0.01, 500]", "tension");
                    }
                }
            }
        }
        for (double t : at) {
            if (!(t >= x[0] && t <= x[x.length - 1])) {
                throw new QfError("E_OUT_OF_RANGE", "query outside the knots", "at");
            }
        }
        double[] values = new double[at.length];
        double[] slopesOut = method.hasDerivatives() ? new double[at.length] : null;
        double[] knotSlopes = switch (m) {
            case CUBIC_NATURAL, CUBIC_CLAMPED, CUBIC_NOT_A_KNOT -> splineSlopes(m, x, y, params);
            case MONOTONE_PCHIP -> pchipSlopes(x, y);
            default -> null;
        };
        double[] curvature = m == Method.TENSION ? tensionCurvature(x, y, p) : null;
        for (int q = 0; q < at.length; q++) {
            double t = at[q];
            int i = interval(x, t);
            double h = x[i + 1] - x[i];
            double u = (t - x[i]) / h;
            switch (m) {
                case LINEAR -> values[q] = y[i] + u * (y[i + 1] - y[i]);
                case LOG_LINEAR -> values[q] = Math.exp((1.0 - u) * Math.log(y[i]) + u * Math.log(y[i + 1]));
                case TENSION -> {
                    double[] s = tensionAt(x, y, curvature, p, i, t);
                    values[q] = s[0];
                    slopesOut[q] = s[1];
                }
                default -> {
                    double u2 = u * u;
                    double u3 = u2 * u;
                    double m0 = knotSlopes[i];
                    double m1 = knotSlopes[i + 1];
                    values[q] = (2 * u3 - 3 * u2 + 1) * y[i] + (u3 - 2 * u2 + u) * h * m0
                            + (-2 * u3 + 3 * u2) * y[i + 1] + (u3 - u2) * h * m1;
                    slopesOut[q] = ((6 * u2 - 6 * u) * (y[i] - y[i + 1])) / h + (3 * u2 - 4 * u + 1) * m0
                            + (3 * u2 - 2 * u) * m1;
                }
            }
        }
        return new Result(values, slopesOut);
    }

    /** Index of the interval for t: a query on an interior knot uses the interval to its right. */
    static int interval(double[] x, double t) {
        int k = Arrays.binarySearch(x, t);
        int i = k >= 0 ? k : -k - 2;
        return Math.max(0, Math.min(i, x.length - 2));
    }

    /** Knot slopes of a C2 cubic spline, from the slope form of the continuity equations. */
    private static double[] splineSlopes(Method m, double[] x, double[] y, Params params) {
        int n = x.length;
        double[] h = new double[n - 1];
        double[] d = new double[n - 1];
        for (int i = 0; i < n - 1; i++) {
            h[i] = x[i + 1] - x[i];
            d[i] = (y[i + 1] - y[i]) / h[i];
        }
        double[] lower = new double[n - 1];
        double[] diag = new double[n];
        double[] upper = new double[n - 1];
        double[] rhs = new double[n];
        for (int i = 1; i < n - 1; i++) {
            lower[i - 1] = h[i];
            diag[i] = 2.0 * (h[i - 1] + h[i]);
            upper[i] = h[i - 1];
            rhs[i] = 3.0 * (h[i] * d[i - 1] + h[i - 1] * d[i]);
        }
        switch (m) {
            case CUBIC_NATURAL -> {
                diag[0] = 2.0;
                upper[0] = 1.0;
                rhs[0] = 3.0 * d[0];
                lower[n - 2] = 1.0;
                diag[n - 1] = 2.0;
                rhs[n - 1] = 3.0 * d[n - 2];
            }
            case CUBIC_CLAMPED -> {
                diag[0] = 1.0;
                upper[0] = 0.0;
                rhs[0] = params.slopeStart();
                lower[n - 2] = 0.0;
                diag[n - 1] = 1.0;
                rhs[n - 1] = params.slopeEnd();
            }
            default -> {
                double h0 = h[0];
                double h1 = h[1];
                diag[0] = h1;
                upper[0] = h0 + h1;
                rhs[0] = ((h0 + 2.0 * (h0 + h1)) * h1 * d[0] + h0 * h0 * d[1]) / (h0 + h1);
                double hb = h[n - 2];
                double ha = h[n - 3];
                diag[n - 1] = ha;
                lower[n - 2] = ha + hb;
                rhs[n - 1] = ((hb + 2.0 * (ha + hb)) * ha * d[n - 2] + hb * hb * d[n - 3]) / (ha + hb);
            }
        }
        return LinearAlgebra.solveTridiagonal(lower, diag, upper, rhs);
    }

    private static double[] pchipSlopes(double[] x, double[] y) {
        int n = x.length;
        double[] h = new double[n - 1];
        double[] d = new double[n - 1];
        for (int i = 0; i < n - 1; i++) {
            h[i] = x[i + 1] - x[i];
            d[i] = (y[i + 1] - y[i]) / h[i];
        }
        double[] m = new double[n];
        if (n == 2) {
            m[0] = d[0];
            m[1] = d[0];
            return m;
        }
        for (int i = 1; i < n - 1; i++) {
            if (d[i - 1] == 0.0 || d[i] == 0.0 || Math.signum(d[i - 1]) != Math.signum(d[i])) {
                m[i] = 0.0;
            } else {
                double w1 = 2.0 * h[i] + h[i - 1];
                double w2 = h[i] + 2.0 * h[i - 1];
                m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i]);
            }
        }
        m[0] = pchipEnd(h[0], h[1], d[0], d[1]);
        m[n - 1] = pchipEnd(h[n - 2], h[n - 3], d[n - 2], d[n - 3]);
        return m;
    }

    private static double pchipEnd(double h0, double h1, double d0, double d1) {
        double m = ((2.0 * h0 + h1) * d0 - h0 * d1) / (h0 + h1);
        if (Math.signum(m) != Math.signum(d0)) {
            return 0.0;
        }
        if (Math.signum(d0) != Math.signum(d1) && Math.abs(m) > 3.0 * Math.abs(d0)) {
            return 3.0 * d0;
        }
        return m;
    }

    private static double[] tensionCurvature(double[] x, double[] y, double p) {
        int n = x.length;
        double[] e = new double[n - 1];
        double[] c = new double[n - 1];
        double[] d = new double[n - 1];
        for (int i = 0; i < n - 1; i++) {
            double h = x[i + 1] - x[i];
            double ph = p * h;
            e[i] = 1.0 / h - p / Math.sinh(ph);
            c[i] = p * Math.cosh(ph) / Math.sinh(ph) - 1.0 / h;
            d[i] = (y[i + 1] - y[i]) / h;
        }
        int k = n - 2; // Interior unknowns M_1 .. M_{n-2}.
        double[] lower = new double[Math.max(k - 1, 0)];
        double[] diag = new double[k];
        double[] upper = new double[Math.max(k - 1, 0)];
        double[] rhs = new double[k];
        for (int i = 1; i <= k; i++) {
            diag[i - 1] = c[i - 1] + c[i];
            rhs[i - 1] = p * p * (d[i] - d[i - 1]);
            if (i < k) {
                upper[i - 1] = e[i];
                lower[i - 1] = e[i];
            }
        }
        double[] inner = LinearAlgebra.solveTridiagonal(lower, diag, upper, rhs);
        double[] m = new double[n];
        System.arraycopy(inner, 0, m, 1, k);
        return m;
    }

    private static double[] tensionAt(double[] x, double[] y, double[] m, double p, int i, double t) {
        double h = x[i + 1] - x[i];
        double left = x[i + 1] - t;
        double right = t - x[i];
        double sh = Math.sinh(p * h);
        double p2 = p * p;
        double a = y[i] - m[i] / p2;
        double b = y[i + 1] - m[i + 1] / p2;
        double s = (m[i] * Math.sinh(p * left) + m[i + 1] * Math.sinh(p * right)) / (p2 * sh)
                + a * left / h + b * right / h;
        double ds = (-m[i] * Math.cosh(p * left) + m[i + 1] * Math.cosh(p * right)) / (p * sh) + (b - a) / h;
        return new double[] {s, ds};
    }
}
