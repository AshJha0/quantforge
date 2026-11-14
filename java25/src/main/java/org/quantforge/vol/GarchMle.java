package org.quantforge.vol;

import java.util.function.ToDoubleFunction;
import org.quantforge.core.Finite;
import org.quantforge.core.QfError;

/**
 * GARCH(1,1) stage F additions (garch.md, "Stage F additions", rulings F-11 to F-14): Student-t innovations scaled to
 * unit variance, a fixed mean, and the maximum-likelihood estimate with observed-information standard errors.
 */
public final class GarchMle {
    private GarchMle() {}

    /** Lanczos coefficients, g = 7, 9 terms. */
    private static final double[] LANCZOS = {
        0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
        12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7};

    /** ln Gamma(x) for x > 0, about 1e-15 relative on [1, 1000]. */
    public static double lnGamma(double x) {
        Finite.check("x", x);
        if (!(x > 0.0)) {
            throw new QfError("E_DOMAIN", "lnGamma needs x > 0", "x");
        }
        if (x < 0.5) {
            return Math.log(Math.PI / Math.sin(Math.PI * x)) - lnGamma(1.0 - x);
        }
        double z = x - 1.0;
        double a = LANCZOS[0];
        double t = z + 7.5;
        for (int i = 1; i < 9; i++) {
            a += LANCZOS[i] / (z + i);
        }
        return 0.5 * Math.log(2.0 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(a);
    }

    /** Digamma for x > 0: recurrence up to 10, then the asymptotic series. */
    static double digamma(double x) {
        double r = 0.0;
        while (x < 10.0) {
            r -= 1.0 / x;
            x += 1.0;
        }
        double f = 1.0 / (x * x);
        return r + Math.log(x) - 0.5 / x
                - f * (1.0 / 12 - f * (1.0 / 120 - f * (1.0 / 252 - f * (1.0 / 240 - f * (1.0 / 132)))));
    }

    /** The t density constant per observation: lnGamma((nu+1)/2) - lnGamma(nu/2) - ln(pi (nu - 2))/2. */
    private static double tConstant(double nu) {
        return lnGamma((nu + 1) / 2) - lnGamma(nu / 2) - 0.5 * Math.log(Math.PI * (nu - 2));
    }

    /**
     * Log-likelihood on residuals {@code e} (already demeaned). {@code nu} is NaN for Gaussian innovations. When
     * {@code grad} is not null it receives d loglik / d (omega, alpha, beta[, nu]).
     */
    static Garch.Path path(double[] e, double omega, double alpha, double beta, double v0, double nu, double[] grad) {
        boolean t = !Double.isNaN(nu);
        double[] v = new double[e.length];
        double s = v0;
        double dw = 0.0;
        double da = 0.0;
        double db = 0.0;
        double ll = 0.0;
        double gw = 0.0;
        double ga = 0.0;
        double gb = 0.0;
        double gn = 0.0;
        double c = t ? tConstant(nu) : -0.5 * Math.log(2.0 * Math.PI);
        double dc = t ? 0.5 * digamma((nu + 1) / 2) - 0.5 * digamma(nu / 2) - 0.5 / (nu - 2) : 0.0;
        for (int i = 0; i < e.length; i++) {
            v[i] = s;
            double e2 = e[i] * e[i];
            double dlds;
            if (t) {
                double q = e2 / ((nu - 2) * s);
                ll += c - 0.5 * Math.log(s) - (nu + 1) / 2 * Math.log1p(q);
                dlds = -0.5 / s + (nu + 1) / 2 * q / (1 + q) / s;
                gn += dc - 0.5 * Math.log1p(q) + (nu + 1) / 2 * q / (nu - 2) / (1 + q);
            } else {
                ll += c - 0.5 * (Math.log(s) + e2 / s);
                dlds = -0.5 * (1.0 / s - e2 / (s * s));
            }
            gw += dlds * dw;
            ga += dlds * da;
            gb += dlds * db;
            // derivatives of the next variance, then the variance itself
            double ndw = 1.0 + beta * dw;
            double nda = e2 + beta * da;
            double ndb = s + beta * db;
            dw = ndw;
            da = nda;
            db = ndb;
            s = omega + alpha * e2 + beta * s;
        }
        if (grad != null) {
            grad[0] = gw;
            grad[1] = ga;
            grad[2] = gb;
            if (t) {
                grad[3] = gn;
            }
        }
        return new Garch.Path(ll, v, s);
    }

    /** {@code vol.garch.loglik} with the stage F options; {@code nu} NaN for NORMAL. */
    public static Garch.Path loglik(double[] r, double omega, double alpha, double beta, double v0, double nu,
                                    double mu) {
        Finite.check("r", r);
        Finite.check("v0", v0);
        Finite.check("mu", mu);
        return path(residuals(r, mu), omega, alpha, beta, v0, nu, null);
    }

    public static double[] residuals(double[] r, double mu) {
        double[] e = new double[r.length];
        for (int i = 0; i < e.length; i++) {
            e[i] = r[i] - mu;
        }
        return e;
    }

    public static double mean(double[] r) {
        double s = 0.0;
        for (double x : r) {
            s += x;
        }
        return s / r.length;
    }

    public record Estimate(double omega, double alpha, double beta, double nu, double mean, double loglik,
                           double[] stdErrors) {}

    private static double logistic(double x) {
        return 1.0 / (1.0 + Math.exp(-x));
    }

    private static double logit(double p) {
        return Math.log(p / (1 - p));
    }

    private static double[] natural(double[] x, boolean t) {
        double p = logistic(x[1]);
        double u = logistic(x[2]);
        double[] q = {Math.exp(x[0]), p * u, p * (1 - u)};
        return t ? new double[] {q[0], q[1], q[2], 2.0 + 498.0 * logistic(x[3])} : q;
    }

    private static double value(double[] e, double v0, double[] p) {
        double nu = p.length == 4 ? p[3] : Double.NaN;
        return path(e, p[0], p[1], p[2], v0, nu, null).loglik();
    }

    private static double[] gradient(double[] e, double v0, double[] p) {
        double[] g = new double[p.length];
        path(e, p[0], p[1], p[2], v0, p.length == 4 ? p[3] : Double.NaN, g);
        return g;
    }

    private static boolean feasible(double[] p) {
        return p[0] > 0 && p[1] >= 0 && p[2] >= 0 && p[1] + p[2] < 1 && (p.length < 4 || (p[3] > 2 && p[3] <= 500));
    }

    /** Central differences of the analytic score, relative step 1e-5 (garch.md allows it). */
    private static double[][] hessian(double[] e, double v0, double[] p) {
        int n = p.length;
        double[][] h = new double[n][n];
        for (int j = 0; j < n; j++) {
            double step = 1e-5 * Math.abs(p[j]);
            double[] up = p.clone();
            double[] dn = p.clone();
            up[j] += step;
            dn[j] -= step;
            double[] gu = gradient(e, v0, up);
            double[] gd = gradient(e, v0, dn);
            for (int i = 0; i < n; i++) {
                h[i][j] = (gu[i] - gd[i]) / (2 * step);
            }
        }
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < i; j++) {
                double m = (h[i][j] + h[j][i]) / 2;
                h[i][j] = m;
                h[j][i] = m;
            }
        }
        return h;
    }

    /** Cholesky of a symmetric positive definite matrix, or null. */
    private static double[][] cholesky(double[][] a) {
        int n = a.length;
        double[][] l = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j <= i; j++) {
                double s = a[i][j];
                for (int k = 0; k < j; k++) {
                    s -= l[i][k] * l[j][k];
                }
                if (i == j) {
                    if (!(s > 0.0)) {
                        return null;
                    }
                    l[i][i] = Math.sqrt(s);
                } else {
                    l[i][j] = s / l[j][j];
                }
            }
        }
        return l;
    }

    private static double[] solve(double[][] l, double[] b) {
        int n = b.length;
        double[] y = new double[n];
        for (int i = 0; i < n; i++) {
            double s = b[i];
            for (int k = 0; k < i; k++) {
                s -= l[i][k] * y[k];
            }
            y[i] = s / l[i][i];
        }
        double[] x = new double[n];
        for (int i = n - 1; i >= 0; i--) {
            double s = y[i];
            for (int k = i + 1; k < n; k++) {
                s -= l[k][i] * x[k];
            }
            x[i] = s / l[i][i];
        }
        return x;
    }

    private static QfError noConvergence() {
        return new QfError("E_NO_CONVERGENCE", "no interior maximum of the GARCH likelihood");
    }

    /** {@code vol.garch.estimate}: the caller has checked the counts and the initial variance. */
    public static Estimate estimate(double[] r, double v0, boolean studentT, boolean demean) {
        Finite.check("r", r);
        double mu = demean ? mean(r) : 0.0;
        double[] e = residuals(r, mu);
        double var = Garch.sampleVariance(e);
        if (!Double.isFinite(var)) { // rulings R6-8.1, J-0b.2: the squares overflow binary64
            throw new QfError("E_NON_FINITE", "the sample variance of the returns overflows", "returns");
        }
        Finite.check("v0", v0);
        if (!(var > 0.0)) {
            throw new QfError("E_DOMAIN", "returns are all zero");
        }
        ToDoubleFunction<double[]> f = x -> {
            double ll = value(e, v0, natural(x, studentT));
            return Double.isFinite(ll) ? -ll : Double.MAX_VALUE;
        };
        double best = Double.POSITIVE_INFINITY;
        double[] bestX = null;
        for (double p : new double[] {0.9, 0.98}) {
            for (double share : new double[] {0.05, 0.15}) {
                double[] x = studentT
                        ? new double[] {Math.log(var * (1 - p)), logit(p), logit(share), logit(6.0 / 498.0)}
                        : new double[] {Math.log(var * (1 - p)), logit(p), logit(share)};
                for (int restart = 0; restart < 4; restart++) {
                    x = Garch.nelderMead(f, x, restart == 0 ? 0.5 : 0.05);
                }
                double y = f.applyAsDouble(x);
                if (y < best) {
                    best = y;
                    bestX = x;
                }
            }
        }
        if (bestX == null || best == Double.MAX_VALUE) {
            throw noConvergence();
        }
        double[] p = natural(bestX, studentT);
        double[][] l = null;
        boolean done = false;
        for (int it = 0; it < 200 && !done; it++) {
            double[][] h = hessian(e, v0, p);
            double[][] neg = new double[p.length][p.length];
            for (int i = 0; i < p.length; i++) {
                for (int j = 0; j < p.length; j++) {
                    neg[i][j] = -h[i][j];
                }
            }
            l = cholesky(neg);
            if (l == null) {
                throw noConvergence();
            }
            double[] step = solve(l, gradient(e, v0, p));
            double lambda = 1.0;
            double[] next = null;
            for (int k = 0; k < 60; k++) {
                double[] c = p.clone();
                for (int i = 0; i < c.length; i++) {
                    c[i] += lambda * step[i];
                }
                if (feasible(c)) {
                    next = c;
                    break;
                }
                lambda /= 2;
            }
            if (next == null) {
                throw noConvergence();
            }
            double rel = 0.0;
            for (int i = 0; i < p.length; i++) {
                rel = Math.max(rel, Math.abs(next[i] - p[i]) / Math.abs(next[i]));
            }
            p = next;
            done = rel < 1e-12;
        }
        if (!done) {
            throw noConvergence();
        }
        // ruling F-11: interior only, at least 1e-6 (relative to scale) from every bound
        double tol = 1e-6;
        if (p[0] < tol * var || p[1] < tol || p[2] < tol || 1 - p[1] - p[2] < tol
                || (studentT && (p[3] - 2 < tol || 500 - p[3] < tol * 500))) {
            throw noConvergence();
        }
        double[][] h = hessian(e, v0, p);
        double[][] neg = new double[p.length][p.length];
        for (int i = 0; i < p.length; i++) {
            for (int j = 0; j < p.length; j++) {
                neg[i][j] = -h[i][j];
            }
        }
        l = cholesky(neg);
        if (l == null) {
            throw noConvergence();
        }
        double[] se = new double[p.length];
        for (int i = 0; i < p.length; i++) {
            double[] unit = new double[p.length];
            unit[i] = 1.0;
            se[i] = Math.sqrt(solve(l, unit)[i]);
        }
        double nu = studentT ? p[3] : Double.NaN;
        double ll = path(e, p[0], p[1], p[2], v0, nu, null).loglik();
        return new Estimate(p[0], p[1], p[2], nu, mu, ll, se);
    }
}
