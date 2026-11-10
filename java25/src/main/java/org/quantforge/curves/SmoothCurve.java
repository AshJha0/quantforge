package org.quantforge.curves;

/**
 * The stage F interpolations on {@code ln S} (curve-framework.md, "Stage F: pluggable interpolation", rulings F-18
 * to F-20). Built once from the node times {@code t[0] = 0 < ... < t[n]} and {@code ln S} at each node. Inside
 * {@code [0, t_n]} it gives {@code ln S(t)} and the right-hand instantaneous forward; beyond {@code t_n} the curve
 * extrapolates with the left-hand forward at the last node.
 */
abstract class SmoothCurve {
    final double[] t;
    final double[] ln;

    SmoothCurve(double[] t, double[] ln) {
        this.t = t;
        this.ln = ln;
    }

    /** The section holding {@code time}: the i with {@code t[i] <= time < t[i+1]}, the last one at {@code t_n}. */
    int section(double time) {
        int lo = 0;
        int hi = t.length - 1;
        if (time >= t[hi]) {
            return hi - 1;
        }
        while (hi - lo > 1) {
            int mid = (lo + hi) >>> 1;
            if (t[mid] <= time) {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    /** ln S at {@code time} in {@code [0, t_n]}. */
    abstract double lnAt(double time);

    /** Right-hand instantaneous forward at {@code time} in {@code [0, t_n)}. */
    abstract double forwardAt(double time);

    /** The left-hand forward at {@code t_n}, used beyond the last node (ruling F-20). */
    abstract double lastForward();

    static SmoothCurve of(Curve.Interpolation m, double[] t, double[] ln, double tension, int stepIndex) {
        return switch (m) {
            case MONOTONE_CONVEX -> new MonotoneConvex(t, ln);
            case MONOTONIC_LOG_CUBIC -> new LogCubic(t, ln);
            case TENSION_SPLINE -> new Tension(t, ln, tension);
            case HYBRID -> new Hybrid(t, ln, stepIndex);
            default -> throw new IllegalArgumentException(m.name());
        };
    }

    /** Hagan-West convex monotone, QuantLib ConvexMonotone(0, 1, forcePositive = false). */
    static final class MonotoneConvex extends SmoothCurve {
        private final double[] y; // y[i] for section i = 1..n (y[0] unused)
        private final double[] f; // node forwards f[0..n]

        MonotoneConvex(double[] t, double[] ln) {
            super(t, ln);
            int n = t.length - 1;
            y = new double[n + 1];
            for (int i = 1; i <= n; i++) {
                y[i] = (ln[i - 1] - ln[i]) / (t[i] - t[i - 1]);
            }
            f = new double[n + 1];
            if (n == 1) {
                f[0] = y[1];
                f[1] = y[1];
            } else {
                for (int i = 1; i < n; i++) {
                    double dl = t[i] - t[i - 1];
                    double dr = t[i + 1] - t[i];
                    f[i] = (dr * y[i] + dl * y[i + 1]) / (dl + dr);
                }
                f[0] = 1.5 * y[1] - 0.5 * f[1];
                f[n] = 1.5 * y[n] - 0.5 * f[n - 1];
            }
        }

        /** {integral from 0 to x, forward at x} of section i (1-based) at local x in [0, 1]. */
        private double[] branch(int i, double x) {
            double yi = y[i];
            double fa = f[i - 1];
            double fb = f[i];
            if (t.length == 2) {
                return new double[] {yi * x, yi};
            }
            double g0 = fa - yi;
            double g1 = fb - yi;
            if (Math.abs(g0) < 1e-14 && Math.abs(g1) < 1e-14) {
                return new double[] {fa * x + (fb - fa) * x * x / 2, fa + (fb - fa) * x};
            }
            if ((g0 > 0 && -2 * g0 <= g1 && g1 <= -0.5 * g0) || (g0 < 0 && -0.5 * g0 <= g1 && g1 <= -2 * g0)) {
                double a = 3 * fa + 3 * fb - 6 * yi;
                double b = -(4 * fa + 2 * fb - 6 * yi);
                return new double[] {a * x * x * x / 3 + b * x * x / 2 + fa * x, a * x * x + b * x + fa};
            }
            if ((g0 < 0 && g1 > -2 * g0) || (g0 > 0 && g1 < -2 * g0)) {
                double eta = (g1 + 2 * g0) / (g1 - g0);
                if (eta < 1) {
                    if (x <= eta) {
                        return new double[] {(yi + g0) * x, yi + g0};
                    }
                    double u = (x - eta) / (1 - eta);
                    return new double[] {(yi + g0) * x + (g1 - g0) * (x - eta) * u * u / 3,
                        yi + g0 + (g1 - g0) * u * u};
                }
                return ruleE(yi, g0, g1, 1.0, x, fa);
            }
            if ((g0 > 0 && g1 < 0 && g1 > -0.5 * g0) || (g0 < 0 && g1 > 0 && g1 < -0.5 * g0)) {
                double eta = 3 * g1 / (g1 - g0);
                if (eta > 0) {
                    if (x <= eta) {
                        double u = (eta - x) / eta;
                        return new double[] {(yi + g1) * x + (g0 - g1) * eta / 3 * (1 - u * u * u),
                            yi + g1 + (g0 - g1) * u * u};
                    }
                    return new double[] {(yi + g1) * x + (g0 - g1) * eta / 3, yi + g1};
                }
                return ruleE(yi, g0, g1, 0.0, x, fa);
            }
            double eta = Math.min(1.0, Math.max(0.0, g1 / (g0 + g1)));
            return ruleE(yi, g0, g1, eta, x, fa);
        }

        private static double[] ruleE(double yi, double g0, double g1, double eta, double x, double fa) {
            double a = -(eta * g0 + (1 - eta) * g1) / 2;
            if (eta == 0.0 && x == 0.0) {
                return new double[] {0.0, fa}; // ruling F-19: the first piece is the point x = 0
            }
            if (x <= eta) {
                double u = (eta - x) / eta;
                return new double[] {(yi + a) * x + (g0 - a) * eta / 3 * (1 - u * u * u), yi + a + (g0 - a) * u * u};
            }
            double u = (x - eta) / (1 - eta);
            return new double[] {(yi + a) * x + (g0 - a) * eta / 3 + (g1 - a) * (x - eta) * u * u / 3,
                yi + a + (g1 - a) * u * u};
        }

        @Override
        double lnAt(double time) {
            int i = section(time) + 1;
            double dx = t[i] - t[i - 1];
            double x = (time - t[i - 1]) / dx;
            if (x >= 1.0) {
                return ln[i];
            }
            return ln[i - 1] - dx * branch(i, x)[0];
        }

        @Override
        double forwardAt(double time) {
            int i = section(time) + 1;
            return branch(i, (time - t[i - 1]) / (t[i] - t[i - 1]))[1];
        }

        @Override
        double lastForward() {
            return branch(t.length - 1, 1.0)[1];
        }
    }

    /** QuantLib MonotonicLogCubic: natural cubic in ln S with the Hyman filter. */
    static final class LogCubic extends SmoothCurve {
        private final double[] m;
        private final double[] b;
        private final double[] c;

        LogCubic(double[] t, double[] ln) {
            super(t, ln);
            int n = t.length - 1;
            double[] h = new double[n];
            double[] s = new double[n];
            for (int i = 0; i < n; i++) {
                h[i] = t[i + 1] - t[i];
                s[i] = (ln[i + 1] - ln[i]) / h[i];
            }
            // tridiagonal system for the unfiltered slopes
            double[] lo = new double[n + 1];
            double[] di = new double[n + 1];
            double[] up = new double[n + 1];
            double[] r = new double[n + 1];
            di[0] = 2;
            up[0] = 1;
            r[0] = 3 * s[0];
            for (int i = 1; i < n; i++) {
                lo[i] = h[i];
                di[i] = 2 * (h[i - 1] + h[i]);
                up[i] = h[i - 1];
                r[i] = 3 * (h[i] * s[i - 1] + h[i - 1] * s[i]);
            }
            lo[n] = 1;
            di[n] = 2;
            r[n] = 3 * s[n - 1];
            double[] raw = thomas(lo, di, up, r);
            m = new double[n + 1];
            for (int i = 0; i <= n; i++) {
                double mi = raw[i];
                if (i == 0 || i == n) {
                    double sl = i == 0 ? s[0] : s[n - 1];
                    m[i] = mi * sl > 0 ? Math.signum(mi) * Math.min(Math.abs(mi), 3 * Math.abs(sl)) : 0.0;
                    continue;
                }
                double p = (s[i - 1] * h[i] + s[i] * h[i - 1]) / (h[i - 1] + h[i]);
                double big = 3 * Math.min(Math.abs(s[i - 1]), Math.min(Math.abs(s[i]), Math.abs(p)));
                if (i > 1 && (s[i - 1] - s[i - 2]) * (s[i] - s[i - 1]) > 0) {
                    double pd = (s[i - 1] * (2 * h[i - 1] + h[i - 2]) - s[i - 2] * h[i - 1]) / (h[i - 2] + h[i - 1]);
                    if (p * pd > 0 && p * (s[i - 1] - s[i - 2]) > 0) {
                        big = Math.max(big, 1.5 * Math.min(Math.abs(p), Math.abs(pd)));
                    }
                }
                if (i < n - 1 && (s[i] - s[i - 1]) * (s[i + 1] - s[i]) > 0) {
                    double pu = (s[i] * (2 * h[i] + h[i + 1]) - s[i + 1] * h[i]) / (h[i] + h[i + 1]);
                    if (p * pu > 0 && -p * (s[i] - s[i - 1]) > 0) {
                        big = Math.max(big, 1.5 * Math.min(Math.abs(p), Math.abs(pu)));
                    }
                }
                m[i] = mi * p > 0 ? Math.signum(mi) * Math.min(Math.abs(mi), big) : 0.0;
            }
            b = new double[n];
            c = new double[n];
            for (int i = 0; i < n; i++) {
                b[i] = (3 * s[i] - m[i + 1] - 2 * m[i]) / h[i];
                c[i] = (m[i + 1] + m[i] - 2 * s[i]) / (h[i] * h[i]);
            }
        }

        @Override
        double lnAt(double time) {
            int i = section(time);
            double d = time - t[i];
            return ln[i] + d * (m[i] + d * (b[i] + d * c[i]));
        }

        @Override
        double forwardAt(double time) {
            int i = section(time);
            double d = time - t[i];
            return -(m[i] + 2 * b[i] * d + 3 * c[i] * d * d);
        }

        @Override
        double lastForward() {
            int i = t.length - 2;
            double d = t[i + 1] - t[i];
            return -(m[i] + 2 * b[i] * d + 3 * c[i] * d * d);
        }
    }

    /** Exponential tension spline in ln S with natural ends. */
    static final class Tension extends SmoothCurve {
        private final double sigma;
        private final double[] mm; // second derivatives M[0..n], ends 0

        Tension(double[] t, double[] ln, double sigma) {
            super(t, ln);
            this.sigma = sigma;
            int n = t.length - 1;
            mm = new double[n + 1];
            if (n < 2) {
                return;
            }
            double[] al = new double[n];
            double[] be = new double[n];
            double[] s = new double[n];
            for (int i = 0; i < n; i++) {
                double h = t[i + 1] - t[i];
                double z = sigma * h;
                s[i] = (ln[i + 1] - ln[i]) / h;
                if (z < 1e-3) {
                    al[i] = h / 6 * (1 - 7 * z * z / 60); // ruling F-35
                    be[i] = h / 3 * (1 - z * z / 15);
                } else {
                    double q = -Math.expm1(-2 * z);
                    double invSinh = 2 * Math.exp(-z) / q;
                    double coth = (1 + Math.exp(-2 * z)) / q;
                    al[i] = 1 / (sigma * sigma * h) - invSinh / sigma;
                    be[i] = coth / sigma - 1 / (sigma * sigma * h);
                }
            }
            int k = n - 1; // unknowns M_1..M_{n-1}
            double[] lo = new double[k];
            double[] di = new double[k];
            double[] up = new double[k];
            double[] r = new double[k];
            for (int j = 0; j < k; j++) {
                int i = j + 1;
                lo[j] = al[i - 1];
                di[j] = be[i - 1] + be[i];
                up[j] = al[i];
                r[j] = s[i] - s[i - 1];
            }
            double[] x = thomas(lo, di, up, r);
            System.arraycopy(x, 0, mm, 1, k);
        }

        /** {R(u), R'(u)} on an interval of length h. */
        private double[] r(double u, double h) {
            double z = sigma * h;
            if (z < 1e-3) {
                // ruling F-35: the z^2 term of R(u) and of its derivative
                double s2 = sigma * sigma;
                double f = (u / h) * (u * u - h * h) / 6;
                double g = 1 + s2 * (3 * u * u - 7 * h * h) / 60;
                return new double[] {f * g, (3 * u * u - h * h) / (6 * h) * g + f * s2 * u / 10};
            }
            double q = -Math.expm1(-2 * z);
            double e = Math.exp(-sigma * (h - u));
            double sinhRatio = e * -Math.expm1(-2 * sigma * u) / q;
            double coshRatio = e * (1 + Math.exp(-2 * sigma * u)) / q;
            double s2 = sigma * sigma;
            return new double[] {(sinhRatio - u / h) / s2, (sigma * coshRatio - 1 / h) / s2};
        }

        private double[] at(int i, double time) {
            double h = t[i + 1] - t[i];
            double a = time - t[i];
            double bb = t[i + 1] - time;
            double[] ra = r(a, h);
            double[] rb = r(bb, h);
            double v = ln[i] * bb / h + ln[i + 1] * a / h + mm[i] * rb[0] + mm[i + 1] * ra[0];
            double d = (ln[i + 1] - ln[i]) / h - mm[i] * rb[1] + mm[i + 1] * ra[1];
            return new double[] {v, d};
        }

        @Override
        double lnAt(double time) {
            return at(section(time), time)[0];
        }

        @Override
        double forwardAt(double time) {
            return -at(section(time), time)[1];
        }

        @Override
        double lastForward() {
            int i = t.length - 2;
            return -at(i, t[i + 1])[1];
        }
    }

    /** Log-linear steps up to node {@code k}, monotone convex on nodes k..n after it. */
    static final class Hybrid extends SmoothCurve {
        private final int k;
        private final MonotoneConvex tail;

        Hybrid(double[] t, double[] ln, int k) {
            super(t, ln);
            this.k = k;
            int n = t.length - 1;
            if (k < n) {
                double[] tt = new double[n - k + 1];
                double[] ll = new double[n - k + 1];
                for (int i = k; i <= n; i++) {
                    tt[i - k] = t[i];
                    ll[i - k] = ln[i];
                }
                tail = new MonotoneConvex(tt, ll);
            } else {
                tail = null;
            }
        }

        private double step(int i) {
            return -(ln[i + 1] - ln[i]) / (t[i + 1] - t[i]);
        }

        @Override
        double lnAt(double time) {
            if (time < t[k] || tail == null) {
                int i = section(time);
                double u = (time - t[i]) / (t[i + 1] - t[i]);
                return u >= 1.0 ? ln[i + 1] : (1 - u) * ln[i] + u * ln[i + 1];
            }
            return tail.lnAt(time);
        }

        @Override
        double forwardAt(double time) {
            if (time < t[k] || tail == null) {
                return step(section(time));
            }
            return tail.forwardAt(time);
        }

        @Override
        double lastForward() {
            return tail == null ? step(t.length - 2) : tail.lastForward();
        }
    }

    /** Thomas algorithm: lo[i] x[i-1] + di[i] x[i] + up[i] x[i+1] = r[i]. */
    static double[] thomas(double[] lo, double[] di, double[] up, double[] r) {
        int n = r.length;
        double[] c = new double[n];
        double[] d = new double[n];
        for (int i = 0; i < n; i++) {
            double w = di[i] - (i > 0 ? lo[i] * c[i - 1] : 0.0);
            c[i] = i < n - 1 ? up[i] / w : 0.0;
            d[i] = (r[i] - (i > 0 ? lo[i] * d[i - 1] : 0.0)) / w;
        }
        double[] x = new double[n];
        for (int i = n - 1; i >= 0; i--) {
            x[i] = d[i] - (i < n - 1 ? c[i] * x[i + 1] : 0.0);
        }
        return x;
    }
}
