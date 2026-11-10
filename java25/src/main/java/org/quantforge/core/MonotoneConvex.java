package org.quantforge.core;

/** Hagan and West monotone-convex forward interpolation (interpolation.md). */
public final class MonotoneConvex {
    private MonotoneConvex() {}

    public record Result(double[] forwards, double[] zeroRates) {}

    private static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(v, hi));
    }

    public static Result evaluate(double[] times, double[] rates, double[] at, boolean positive) {
        Finite.check("times", times);
        Finite.check("rates", rates);
        Finite.check("at", at);
        int n = times.length;
        if (n != rates.length || n < 2 || !(times[0] > 0.0)) {
            throw new QfError("E_INPUT", "need at least 2 matching points with t_1 > 0");
        }
        for (int i = 1; i < n; i++) {
            if (!(times[i] > times[i - 1])) {
                throw new QfError("E_INPUT", "times not strictly increasing", "t");
            }
        }
        for (double s : at) {
            if (!(s > 0.0 && s <= times[n - 1])) {
                throw new QfError("E_OUT_OF_RANGE", "query outside (0, t_n]", "at");
            }
        }
        double[] t = new double[n + 1];
        double[] rt = new double[n + 1];
        for (int i = 1; i <= n; i++) {
            t[i] = times[i - 1];
            rt[i] = rates[i - 1] * times[i - 1];
        }
        double[] fd = new double[n + 1];
        for (int i = 1; i <= n; i++) {
            fd[i] = (rt[i] - rt[i - 1]) / (t[i] - t[i - 1]);
        }
        double[] f = new double[n + 1];
        for (int i = 1; i < n; i++) {
            double span = t[i + 1] - t[i - 1];
            f[i] = (t[i] - t[i - 1]) / span * fd[i + 1] + (t[i + 1] - t[i]) / span * fd[i];
        }
        f[0] = fd[1] - (f[1] - fd[1]) / 2.0;
        f[n] = fd[n] - (f[n - 1] - fd[n]) / 2.0;
        if (positive) {
            for (int i = 1; i <= n; i++) {
                if (fd[i] < 0.0) {
                    throw new QfError("E_DOMAIN", "positive needs non-negative discrete forwards");
                }
            }
            f[0] = clamp(f[0], 0.0, 2.0 * fd[1]);
            for (int i = 1; i < n; i++) {
                f[i] = clamp(f[i], 0.0, 2.0 * Math.min(fd[i], fd[i + 1]));
            }
            f[n] = clamp(f[n], 0.0, 2.0 * fd[n]);
        }
        double[] forwards = new double[at.length];
        double[] zeros = new double[at.length];
        for (int q = 0; q < at.length; q++) {
            double s = at[q];
            int i = 1;
            while (s > t[i]) {
                i++;
            }
            double h = t[i] - t[i - 1];
            double x = (s - t[i - 1]) / h;
            double[] g = shape(f[i - 1] - fd[i], f[i] - fd[i], x);
            forwards[q] = fd[i] + g[0];
            zeros[q] = (rt[i - 1] + h * (fd[i] * x + g[1])) / s;
        }
        return new Result(forwards, zeros);
    }

    /** Integral from 0 to x of ((eta - y)/eta)^2. */
    private static double fallingIntegral(double eta, double x) {
        double r = (eta - x) / eta;
        return eta / 3.0 * (1.0 - r * r * r);
    }

    /** Returns g(x) and its integral G(x). */
    static double[] shape(double g0, double g1, double x) {
        if (g0 == 0.0 && g1 == 0.0) {
            return new double[] {0.0, 0.0};
        }
        if ((g0 < 0.0 && -g0 / 2.0 <= g1 && g1 <= -2.0 * g0) || (g0 > 0.0 && -g0 / 2.0 >= g1 && g1 >= -2.0 * g0)) {
            double x2 = x * x;
            double x3 = x2 * x;
            return new double[] {g0 * (1.0 - 4.0 * x + 3.0 * x2) + g1 * (-2.0 * x + 3.0 * x2),
                g0 * (x - 2.0 * x2 + x3) + g1 * (-x2 + x3)};
        }
        if ((g0 < 0.0 && g1 > -2.0 * g0) || (g0 > 0.0 && g1 < -2.0 * g0)) {
            double eta = (g1 + 2.0 * g0) / (g1 - g0);
            if (x <= eta) {
                return new double[] {g0, g0 * x};
            }
            double w = (x - eta) / (1.0 - eta);
            return new double[] {g0 + (g1 - g0) * w * w, g0 * x + (g1 - g0) * w * w * (x - eta) / 3.0};
        }
        if ((g0 > 0.0 && -g0 / 2.0 < g1 && g1 < 0.0) || (g0 < 0.0 && 0.0 < g1 && g1 < -g0 / 2.0)) {
            double eta = 3.0 * g1 / (g1 - g0);
            if (x < eta) {
                double r = (eta - x) / eta;
                return new double[] {g1 + (g0 - g1) * r * r, g1 * x + (g0 - g1) * fallingIntegral(eta, x)};
            }
            return new double[] {g1, g1 * x + (g0 - g1) * eta / 3.0};
        }
        double eta = g1 / (g1 + g0);
        double a = -g0 * g1 / (g0 + g1);
        if (x < eta) {
            double r = (eta - x) / eta;
            return new double[] {a + (g0 - a) * r * r, a * x + (g0 - a) * fallingIntegral(eta, x)};
        }
        if (eta == 1.0) {
            // g0 = 0 at x = 1: the table's 0/0. The node forward is the limit, so that f stays continuous there.
            return new double[] {g1, a * x + (g0 - a) / 3.0};
        }
        double w = (x - eta) / (1.0 - eta);
        return new double[] {a + (g1 - a) * w * w, a * x + (g0 - a) * eta / 3.0 + (g1 - a) * w * w * (x - eta) / 3.0};
    }
}
