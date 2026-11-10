package org.quantforge.vol;

import org.quantforge.core.Finite;

import java.util.Arrays;
import java.util.function.ToDoubleFunction;
import org.quantforge.core.QfError;

/** GARCH(1,1): Gaussian likelihood, variance forecast and maximum-likelihood fit (garch.md, E-B1, E-B2). */
public final class Garch {
    private Garch() {}

    public static final int MIN_FIT_RETURNS = 30;

    public record Path(double loglik, double[] variances, double next) {}

    /** {@code (1/n) sum r^2}: divisor n, no demeaning (ruling E-B1). */
    public static double sampleVariance(double[] r) {
        Finite.check("r", r);
        double s = 0.0;
        for (double x : r) {
            s += x * x;
        }
        return s / r.length;
    }

    public static void checkParameters(double omega, double alpha, double beta) {
        Finite.check("omega", omega);
        Finite.check("alpha", alpha);
        Finite.check("beta", beta);
        if (!(omega > 0.0) || !(alpha >= 0.0) || !(beta >= 0.0)) {
            throw new QfError("E_DOMAIN", "need omega > 0, alpha >= 0, beta >= 0");
        }
    }

    /** The recursion and its likelihood, every term from t = 1 and the ln(2 pi) constant kept. */
    public static Path path(double[] r, double omega, double alpha, double beta, double v0) {
        Finite.check("r", r);
        Finite.check("omega", omega);
        Finite.check("alpha", alpha);
        Finite.check("beta", beta);
        Finite.check("v0", v0);
        double[] v = new double[r.length];
        double s = v0;
        double ll = 0.0;
        double c = Math.log(2.0 * Math.PI);
        for (int t = 0; t < r.length; t++) {
            v[t] = s;
            ll += c + Math.log(s) + r[t] * r[t] / s;
            s = omega + alpha * r[t] * r[t] + beta * s;
        }
        return new Path(-0.5 * ll, v, s);
    }

    public record Forecast(double[] variances, double total, double annualizedVol, double longRun) {}

    public static Forecast forecast(double omega, double alpha, double beta, double next, int h, double ppy) {
        Finite.check("omega", omega);
        Finite.check("alpha", alpha);
        Finite.check("beta", beta);
        Finite.check("next", next);
        Finite.check("ppy", ppy);
        double p = alpha + beta;
        double vl = omega / (1.0 - p);
        double[] v = new double[h];
        double total = 0.0;
        double pk = 1.0;
        for (int i = 0; i < h; i++) {
            v[i] = vl + pk * (next - vl);
            total += v[i];
            pk *= p;
        }
        return new Forecast(v, total, Math.sqrt(total * ppy / h), vl);
    }

    /** Maximum log-likelihood over omega > 0, alpha, beta >= 0, alpha + beta < 1, initial variance fixed. */
    public static double fit(double[] r, double v0) {
        Finite.check("r", r);
        Finite.check("v0", v0);
        double var = sampleVariance(r);
        if (!(var > 0.0)) {
            throw new QfError("E_DOMAIN", "returns are all zero");
        }
        // x = (ln omega, logit of persistence p, logit of the alpha share of p)
        ToDoubleFunction<double[]> f = x -> {
            double p = logistic(x[1]);
            double u = logistic(x[2]);
            double ll = path(r, Math.exp(x[0]), p * u, p * (1 - u), v0).loglik();
            return Double.isFinite(ll) ? -ll : Double.MAX_VALUE;
        };
        double best = Double.POSITIVE_INFINITY;
        double[] bestX = null;
        for (double p : new double[] {0.5, 0.9, 0.98}) {
            for (double share : new double[] {0.05, 0.15, 0.4}) {
                double[] x = {Math.log(var * (1 - p)), logit(p), logit(share)};
                for (int restart = 0; restart < 6; restart++) {
                    x = nelderMead(f, x, restart == 0 ? 0.5 : 0.05);
                }
                double y = f.applyAsDouble(x);
                if (y < best) {
                    best = y;
                    bestX = x;
                }
            }
        }
        if (bestX == null || !Double.isFinite(best) || best == Double.MAX_VALUE) {
            throw new QfError("E_NO_CONVERGENCE", "GARCH fit did not converge");
        }
        return -best;
    }

    private static double logistic(double x) {
        return 1.0 / (1.0 + Math.exp(-x));
    }

    private static double logit(double p) {
        return Math.log(p / (1 - p));
    }

    /** Nelder-Mead with standard coefficients, to a simplex spread of 1e-14 in value. */
    static double[] nelderMead(ToDoubleFunction<double[]> f, double[] x0, double step) {
        int n = x0.length;
        double[][] s = new double[n + 1][];
        double[] y = new double[n + 1];
        for (int i = 0; i <= n; i++) {
            s[i] = x0.clone();
            if (i > 0) {
                s[i][i - 1] += step;
            }
            y[i] = f.applyAsDouble(s[i]);
        }
        for (int it = 0; it < 5000; it++) {
            Integer[] o = new Integer[n + 1];
            for (int i = 0; i <= n; i++) {
                o[i] = i;
            }
            double[] yy = y;
            Arrays.sort(o, (a, b) -> Double.compare(yy[a], yy[b]));
            double[][] s2 = new double[n + 1][];
            double[] y2 = new double[n + 1];
            for (int i = 0; i <= n; i++) {
                s2[i] = s[o[i]];
                y2[i] = y[o[i]];
            }
            s = s2;
            y = y2;
            if (Math.abs(y[n] - y[0]) <= 1e-14 * (1 + Math.abs(y[0]))) {
                break;
            }
            double[] c = new double[n];
            for (int i = 0; i < n; i++) {
                for (int d = 0; d < n; d++) {
                    c[d] += s[i][d] / n;
                }
            }
            double[] xr = move(c, s[n], -1.0);
            double yr = f.applyAsDouble(xr);
            if (yr < y[0]) {
                double[] xe = move(c, s[n], -2.0);
                double ye = f.applyAsDouble(xe);
                s[n] = ye < yr ? xe : xr;
                y[n] = Math.min(ye, yr);
            } else if (yr < y[n - 1]) {
                s[n] = xr;
                y[n] = yr;
            } else {
                double[] xc = yr < y[n] ? move(c, s[n], -0.5) : move(c, s[n], 0.5);
                double yc = f.applyAsDouble(xc);
                if (yc < Math.min(yr, y[n])) {
                    s[n] = xc;
                    y[n] = yc;
                } else {
                    for (int i = 1; i <= n; i++) {
                        s[i] = move(s[0], s[i], 0.5);
                        y[i] = f.applyAsDouble(s[i]);
                    }
                }
            }
        }
        int b = 0;
        for (int i = 1; i <= n; i++) {
            if (y[i] < y[b]) {
                b = i;
            }
        }
        return s[b];
    }

    /** c + t (x - c). */
    private static double[] move(double[] c, double[] x, double t) {
        double[] out = new double[c.length];
        for (int d = 0; d < c.length; d++) {
            out[d] = c[d] + t * (x[d] - c[d]);
        }
        return out;
    }
}
