package org.quantforge.research;

import org.quantforge.core.QfError;

/**
 * Stage J wave 2: mean-variance, risk parity and Euler contributions (07-portfolio/optimisation.md), Ledoit-Wolf
 * and Black-Litterman (07-portfolio/estimation.md), the Acerbi-Szekely Z2 statistic (06-risk/es-backtest.md) and
 * Baum-Welch (11-research/baum-welch.md). Rulings J-W2-1 to J-W2-15. Shapes are checked by the caller.
 */
public final class Allocation {
    private Allocation() {}

    private static QfError domain(String why) {
        return new QfError("E_DOMAIN", why);
    }

    private static QfError input(String why) {
        return new QfError("E_INPUT", why);
    }

    // ---- shared linear algebra ----

    /** True if m is n x n. */
    public static boolean square(double[][] m, int n) {
        if (m.length != n) {
            return false;
        }
        for (double[] r : m) {
            if (r.length != n) {
                return false;
            }
        }
        return true;
    }

    /** Ruling J-W2-3: symmetry within 1e-12 max|S|, then a copy built from the upper triangle. */
    public static double[][] symmetric(double[][] s) {
        int n = s.length;
        double big = 0;
        for (double[] r : s) {
            for (double v : r) {
                big = Math.max(big, Math.abs(v));
            }
        }
        double[][] out = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = i; j < n; j++) {
                if (Math.abs(s[i][j] - s[j][i]) > 1e-12 * big) {
                    throw domain("matrix is not symmetric");
                }
                out[i][j] = s[i][j];
                out[j][i] = s[i][j];
            }
        }
        return out;
    }

    /** Lower Cholesky factor; any pivot not above 0 is E_DOMAIN (J-W2-3). */
    public static double[][] cholesky(double[][] a) {
        int n = a.length;
        double[][] l = new double[n][n];
        for (int j = 0; j < n; j++) {
            double d = a[j][j];
            for (int k = 0; k < j; k++) {
                d -= l[j][k] * l[j][k];
            }
            if (!(d > 0)) {
                throw domain("matrix is not positive definite");
            }
            double ljj = Math.sqrt(d);
            l[j][j] = ljj;
            for (int i = j + 1; i < n; i++) {
                double s = a[i][j];
                for (int k = 0; k < j; k++) {
                    s -= l[i][k] * l[j][k];
                }
                l[i][j] = s / ljj;
            }
        }
        return l;
    }

    /** Solves L L' x = b. */
    public static double[] solve(double[][] l, double[] b) {
        int n = b.length;
        double[] y = new double[n];
        for (int i = 0; i < n; i++) {
            double s = b[i];
            for (int k = 0; k < i; k++) {
                s -= l[i][k] * y[k];
            }
            y[i] = s / l[i][i];
        }
        for (int i = n - 1; i >= 0; i--) {
            double s = y[i];
            for (int k = i + 1; k < n; k++) {
                s -= l[k][i] * y[k];
            }
            y[i] = s / l[i][i];
        }
        return y;
    }

    private static double[] mul(double[][] a, double[] x) {
        double[] out = new double[a.length];
        for (int i = 0; i < a.length; i++) {
            double s = 0;
            for (int j = 0; j < x.length; j++) {
                s += a[i][j] * x[j];
            }
            out[i] = s;
        }
        return out;
    }

    private static double dot(double[] a, double[] b) {
        double s = 0;
        for (int i = 0; i < a.length; i++) {
            s += a[i] * b[i];
        }
        return s;
    }

    // ---- mean-variance ----

    /** Mean-variance result (optimisation.md). */
    public record MeanVariance(double[] weights, double expectedReturn, double volatility, double objective,
            long[] atBound) {}

    /** Domain checks in the page's order after shapes: gamma, bounds, feasibility, symmetry, Cholesky. */
    public static MeanVariance meanVariance(double[] mu, double[][] cov, double gamma, double[] lo, double[] hi) {
        int n = mu.length;
        if (!(gamma > 0)) {
            throw domain("risk_aversion must be positive");
        }
        double sl = 0;
        double su = 0;
        for (int i = 0; i < n; i++) {
            if (lo[i] > hi[i]) {
                throw domain("lower above upper");
            }
            sl += lo[i];
            su += hi[i];
        }
        if (sl > 1 || su < 1) {
            throw domain("bounds are infeasible");
        }
        double[][] s = symmetric(cov);
        cholesky(s);
        double[] w = feasibleStart(lo, hi);
        // state: 0 free, -1 at lower, +1 at upper
        int[] state = new int[n];
        int freeIdx = -1;
        for (int i = 0; i < n; i++) {
            if (w[i] == lo[i]) {
                state[i] = -1;
            } else if (w[i] == hi[i]) {
                state[i] = 1;
            } else {
                freeIdx = i;
            }
        }
        if (freeIdx < 0) {
            // all at bounds: one index stays free so the budget multiplier is defined
            freeIdx = n - 1;
            state[freeIdx] = 0;
        }
        for (int iter = 0; iter < 50 * n + 100; iter++) {
            int nf = 0;
            for (int v : state) {
                if (v == 0) {
                    nf++;
                }
            }
            int[] f = new int[nf];
            for (int i = 0, k = 0; i < n; i++) {
                if (state[i] == 0) {
                    f[k++] = i;
                }
            }
            double r = 1;
            for (int i = 0; i < n; i++) {
                if (state[i] != 0) {
                    r -= w[i];
                }
            }
            double[][] sff = new double[nf][nf];
            double[] c = new double[nf];
            double[] ones = new double[nf];
            for (int a = 0; a < nf; a++) {
                ones[a] = 1;
                double cw = 0;
                for (int j = 0; j < n; j++) {
                    if (state[j] != 0) {
                        cw += s[f[a]][j] * w[j];
                    }
                }
                c[a] = mu[f[a]] - gamma * cw;
                for (int b = 0; b < nf; b++) {
                    sff[a][b] = s[f[a]][f[b]];
                }
            }
            double[][] l = cholesky(sff);
            double[] av = solve(l, c);
            double[] ev = solve(l, ones);
            double nu = (sum(av) - gamma * r) / sum(ev);
            double[] target = new double[nf];
            for (int a = 0; a < nf; a++) {
                target[a] = (av[a] - nu * ev[a]) / gamma;
            }
            double alpha = 1;
            int block = -1;
            int blockSide = 0;
            for (int a = 0; a < nf; a++) {
                int i = f[a];
                double p = target[a] - w[i];
                if (p < 0 && target[a] < lo[i]) {
                    double t = (lo[i] - w[i]) / p;
                    if (t < alpha) {
                        alpha = t;
                        block = i;
                        blockSide = -1;
                    }
                } else if (p > 0 && target[a] > hi[i]) {
                    double t = (hi[i] - w[i]) / p;
                    if (t < alpha) {
                        alpha = t;
                        block = i;
                        blockSide = 1;
                    }
                }
            }
            if (block >= 0) {
                for (int a = 0; a < nf; a++) {
                    w[f[a]] += alpha * (target[a] - w[f[a]]);
                }
                w[block] = blockSide < 0 ? lo[block] : hi[block];
                state[block] = blockSide;
                if (nf == 1) {
                    // cannot happen for a feasible budget; guard against a loop
                    break;
                }
                continue;
            }
            for (int a = 0; a < nf; a++) {
                w[f[a]] = target[a];
            }
            double[] sw = mul(s, w);
            int worst = -1;
            double worstG = 0;
            for (int i = 0; i < n; i++) {
                if (state[i] == 0) {
                    continue;
                }
                double g = mu[i] - gamma * sw[i] - nu;
                double viol = state[i] < 0 ? g : -g;
                if (viol > worstG) {
                    worstG = viol;
                    worst = i;
                }
            }
            if (worst < 0) {
                break;
            }
            state[worst] = 0;
        }
        long[] at = new long[n];
        for (int i = 0; i < n; i++) {
            at[i] = w[i] == lo[i] ? -1 : w[i] == hi[i] ? 1 : 0;
        }
        double ret = dot(mu, w);
        double var = dot(w, mul(s, w));
        return new MeanVariance(w, ret, Math.sqrt(var), ret - gamma / 2 * var, at);
    }

    private static double sum(double[] x) {
        double s = 0;
        for (double v : x) {
            s += v;
        }
        return s;
    }

    private static double[] feasibleStart(double[] lo, double[] hi) {
        int n = lo.length;
        double[] w = lo.clone();
        double rest = 1 - sum(lo);
        for (int i = 0; i < n && rest > 0; i++) {
            double room = hi[i] - lo[i];
            if (room >= rest) {
                w[i] = lo[i] + rest;
                rest = 0;
            } else {
                w[i] = hi[i];
                rest -= room;
            }
        }
        return w;
    }

    // ---- risk parity ----

    /** Risk-parity result. */
    public record RiskParity(double[] weights, double volatility, double[] contributions) {}

    /** Budgets null means 1/N each. Checks after shapes: budgets, symmetry, Cholesky (J-W2-5). */
    public static RiskParity riskParity(double[][] cov, double[] budgets) {
        int n = cov.length;
        double[] b = budgets == null ? new double[n] : budgets.clone();
        if (budgets == null) {
            java.util.Arrays.fill(b, 1.0 / n);
        }
        for (double v : b) {
            if (!(v > 0)) {
                throw domain("budgets must be positive");
            }
        }
        double sb = sum(b);
        if (budgets != null && Math.abs(sb - 1) > 1e-12) {
            throw domain("budgets must sum to 1");
        }
        for (int i = 0; i < n; i++) {
            b[i] /= sb;
        }
        double[][] s = symmetric(cov);
        cholesky(s);
        double[] y = new double[n];
        for (int i = 0; i < n; i++) {
            y[i] = Math.sqrt(b[i] / s[i][i]);
        }
        double bn = Math.sqrt(dot(b, b));
        for (int iter = 0; iter < 500; iter++) {
            double[] sy = mul(s, y);
            double[] fv = new double[n];
            for (int i = 0; i < n; i++) {
                fv[i] = sy[i] - b[i] / y[i];
            }
            if (Math.sqrt(dot(fv, fv)) < 1e-14 * bn) {
                break;
            }
            double[][] j = new double[n][n];
            for (int i = 0; i < n; i++) {
                j[i] = s[i].clone();
                j[i][i] += b[i] / (y[i] * y[i]);
            }
            double[] neg = new double[n];
            for (int i = 0; i < n; i++) {
                neg[i] = -fv[i];
            }
            double[] d = solve(cholesky(j), neg);
            double t = 1;
            boolean ok;
            do {
                ok = true;
                for (int i = 0; i < n; i++) {
                    if (!(y[i] + t * d[i] > 0)) {
                        ok = false;
                        t /= 2;
                        break;
                    }
                }
            } while (!ok);
            double step = 0;
            for (int i = 0; i < n; i++) {
                y[i] += t * d[i];
                step = Math.max(step, Math.abs(t * d[i]));
            }
            if (step < 1e-15) {
                break;
            }
        }
        double sy = sum(y);
        double[] w = new double[n];
        for (int i = 0; i < n; i++) {
            w[i] = y[i] / sy;
        }
        Euler e = euler(w, s);
        return new RiskParity(w, e.volatility(), e.contributions());
    }

    // ---- Euler ----

    /** Euler contributions (J-W2-6). */
    public record Euler(double volatility, double[] marginal, double[] contributions, double[] shares) {}

    /** Symmetry and the variance sign are checked here. */
    public static Euler euler(double[] w, double[][] cov) {
        double[][] s = symmetric(cov);
        int n = w.length;
        double[] sw = mul(s, w);
        double var = dot(w, sw);
        if (!(var > 0)) {
            throw domain("portfolio variance must be positive");
        }
        double sigma = Math.sqrt(var);
        double[] m = new double[n];
        double[] c = new double[n];
        double[] sh = new double[n];
        for (int i = 0; i < n; i++) {
            m[i] = sw[i] / sigma;
            c[i] = w[i] * sw[i] / sigma;
            sh[i] = c[i] / sigma;
        }
        return new Euler(sigma, m, c, sh);
    }

    // ---- Ledoit-Wolf ----

    /** Ledoit-Wolf result (J-W2-7). */
    public record LedoitWolf(double[][] covariance, double shrinkage, double mu) {}

    public static LedoitWolf ledoitWolf(double[][] r) {
        int t = r.length;
        if (t < 2) {
            throw input("at least two rows required");
        }
        int n = r[0].length;
        if (n < 1) {
            throw input("at least one column required");
        }
        for (double[] row : r) {
            if (row.length != n) {
                throw input("rows must have equal length");
            }
        }
        double[][] x = new double[t][n];
        for (int j = 0; j < n; j++) {
            double m = 0;
            for (int k = 0; k < t; k++) {
                m += r[k][j];
            }
            m /= t;
            for (int k = 0; k < t; k++) {
                x[k][j] = r[k][j] - m;
            }
        }
        double[][] s = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                double v = 0;
                for (int k = 0; k < t; k++) {
                    v += x[k][i] * x[k][j];
                }
                s[i][j] = v / t;
            }
        }
        double tr = 0;
        for (int i = 0; i < n; i++) {
            tr += s[i][i];
        }
        double mu = tr / n;
        double d2 = 0;
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                double v = s[i][j] - (i == j ? mu : 0);
                d2 += v * v;
            }
        }
        d2 /= n;
        double bb = 0;
        for (int k = 0; k < t; k++) {
            double acc = 0;
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    double v = x[k][i] * x[k][j] - s[i][j];
                    acc += v * v;
                }
            }
            bb += acc;
        }
        bb = bb / ((double) t * t) / n;
        double b2 = Math.min(bb, d2);
        double delta = b2 == 0 ? 0 : b2 / d2;
        double[][] out = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                out[i][j] = (1 - delta) * s[i][j] + (i == j ? delta * mu : 0);
            }
        }
        return new LedoitWolf(out, delta, mu);
    }

    // ---- Black-Litterman ----

    /** Black-Litterman result (J-W2-8). */
    public record BlackLitterman(double[] posteriorReturns, double[][] posteriorCovariance,
            double[][] predictiveCovariance) {}

    /** Checks after shapes: tau, Sigma, Omega. */
    public static BlackLitterman blackLitterman(double[][] cov, double[] pi, double[][] p, double[] q,
            double[][] omega, double tau) {
        if (!(tau > 0)) {
            throw domain("tau must be positive");
        }
        double[][] s = symmetric(cov);
        cholesky(s);
        double[][] om = symmetric(omega);
        cholesky(om);
        int n = pi.length;
        int k = q.length;
        double[][] a = new double[n][k]; // tau Sigma P'
        for (int i = 0; i < n; i++) {
            for (int v = 0; v < k; v++) {
                double acc = 0;
                for (int j = 0; j < n; j++) {
                    acc += s[i][j] * p[v][j];
                }
                a[i][v] = tau * acc;
            }
        }
        double[][] m = new double[k][k];
        for (int u = 0; u < k; u++) {
            for (int v = 0; v < k; v++) {
                double acc = 0;
                for (int j = 0; j < n; j++) {
                    acc += p[u][j] * a[j][v];
                }
                m[u][v] = acc + om[u][v];
            }
        }
        double[][] l = cholesky(m);
        double[] resid = new double[k];
        for (int v = 0; v < k; v++) {
            resid[v] = q[v] - dot(p[v], pi);
        }
        double[] z = solve(l, resid);
        double[] post = new double[n];
        for (int i = 0; i < n; i++) {
            post[i] = pi[i] + dot(a[i], z);
        }
        double[][] sol = new double[n][]; // M^-1 A' rows: sol[j] = M^-1 a[j]
        for (int j = 0; j < n; j++) {
            sol[j] = solve(l, a[j]);
        }
        double[][] pc = new double[n][n];
        double[][] pred = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                pc[i][j] = tau * s[i][j] - dot(a[i], sol[j]);
                pred[i][j] = s[i][j] + pc[i][j];
            }
        }
        return new BlackLitterman(post, pc, pred);
    }

    // ---- ES backtest ----

    /** Z2 result (J-W2-10). */
    public record Z2(double z2, long exceptions, double expectedExceptions) {}

    public static Z2 esZ2(double[] loss, double[] var, double[] es, double alpha) {
        int t = loss.length;
        if (t == 0 || var.length != t || es.length != t) {
            throw input("losses, var and es must have one equal non-zero length");
        }
        if (!(alpha > 0 && alpha < 1)) {
            throw domain("alpha must lie in (0, 1)");
        }
        for (double e : es) {
            if (!(e > 0)) {
                throw domain("es must be positive");
            }
        }
        double acc = 0;
        long ex = 0;
        for (int i = 0; i < t; i++) {
            if (loss[i] > var[i]) {
                ex++;
                acc += loss[i] / (t * alpha * es[i]);
            }
        }
        return new Z2(1 - acc, ex, t * alpha);
    }

    // ---- Baum-Welch ----

    /** Baum-Welch result (J-W2-11). */
    public record BaumWelch(double[] initial, double[][] transition, double[] means, double[] sds,
            double logLikelihood, long iterations, boolean converged) {}

    private record EStep(double ll, double[][] gamma, double[][] xiSum) {}

    private static final double INV_SQRT_2PI = 0.3989422804014327;

    /** Domain checks after shapes: probabilities, row sums, sds, tolerance; then the run (J-W2-13). */
    public static BaumWelch baumWelch(double[] y, double[] pi0, double[][] a0, double[] mu0, double[] sd0,
            double tol, int maxIter) {
        int k = pi0.length;
        checkRow(pi0);
        for (double[] row : a0) {
            checkRow(row);
        }
        for (double s : sd0) {
            if (!(s > 0)) {
                throw domain("sds must be positive");
            }
        }
        if (!(tol > 0)) {
            throw domain("tolerance must be positive");
        }
        double[] pi = pi0.clone();
        double[][] a = new double[k][];
        for (int i = 0; i < k; i++) {
            a[i] = a0[i].clone();
        }
        double[] mu = mu0.clone();
        double[] sd = sd0.clone();
        EStep e = eStep(y, pi, a, mu, sd);
        int iter = 0;
        boolean conv = false;
        while (iter < maxIter) {
            iter++;
            int t = y.length;
            double[] npi = new double[k];
            double[][] na = new double[k][k];
            double[] nmu = new double[k];
            double[] nsd = new double[k];
            for (int i = 0; i < k; i++) {
                npi[i] = e.gamma()[0][i];
                double den = 0;
                for (int s = 0; s < t - 1; s++) {
                    den += e.gamma()[s][i];
                }
                if (!(den > 0)) {
                    throw domain("zero denominator in the transition update");
                }
                for (int j = 0; j < k; j++) {
                    na[i][j] = e.xiSum()[i][j] / den;
                }
                double g = 0;
                double gy = 0;
                for (int s = 0; s < t; s++) {
                    g += e.gamma()[s][i];
                    gy += e.gamma()[s][i] * y[s];
                }
                double m = gy / g;
                double v = 0;
                for (int s = 0; s < t; s++) {
                    double d = y[s] - m;
                    v += e.gamma()[s][i] * d * d;
                }
                v /= g;
                if (!(v > 0)) {
                    throw domain("variance collapsed to zero");
                }
                nmu[i] = m;
                nsd[i] = Math.sqrt(v);
            }
            pi = npi;
            a = na;
            mu = nmu;
            sd = nsd;
            EStep ne = eStep(y, pi, a, mu, sd);
            double gain = ne.ll() - e.ll();
            e = ne;
            if (gain < tol) {
                conv = true;
                break;
            }
        }
        return new BaumWelch(pi, a, mu, sd, e.ll(), iter, conv);
    }

    private static void checkRow(double[] row) {
        double s = 0;
        for (double v : row) {
            if (v < 0) {
                throw domain("negative probability");
            }
            s += v;
        }
        if (Math.abs(s - 1) > 1e-9) {
            throw domain("probabilities must sum to 1");
        }
    }

    private static EStep eStep(double[] y, double[] pi, double[][] a, double[] mu, double[] sd) {
        int t = y.length;
        int k = pi.length;
        double[][] b = new double[t][k];
        for (int s = 0; s < t; s++) {
            for (int j = 0; j < k; j++) {
                double z = (y[s] - mu[j]) / sd[j];
                b[s][j] = INV_SQRT_2PI / sd[j] * Math.exp(-0.5 * z * z);
            }
        }
        double[][] al = new double[t][k];
        double[] c = new double[t];
        double ll = 0;
        for (int s = 0; s < t; s++) {
            double cs = 0;
            for (int j = 0; j < k; j++) {
                double v;
                if (s == 0) {
                    v = pi[j] * b[0][j];
                } else {
                    double acc = 0;
                    for (int i = 0; i < k; i++) {
                        acc += al[s - 1][i] * a[i][j];
                    }
                    v = acc * b[s][j];
                }
                al[s][j] = v;
                cs += v;
            }
            if (!(cs > 0)) {
                throw domain("observations have zero density under every state");
            }
            for (int j = 0; j < k; j++) {
                al[s][j] /= cs;
            }
            c[s] = cs;
            ll += Math.log(cs);
        }
        double[][] be = new double[t][k];
        java.util.Arrays.fill(be[t - 1], 1.0);
        for (int s = t - 2; s >= 0; s--) {
            for (int i = 0; i < k; i++) {
                double acc = 0;
                for (int j = 0; j < k; j++) {
                    acc += a[i][j] * b[s + 1][j] * be[s + 1][j];
                }
                be[s][i] = acc / c[s + 1];
            }
        }
        double[][] g = new double[t][k];
        for (int s = 0; s < t; s++) {
            for (int i = 0; i < k; i++) {
                g[s][i] = al[s][i] * be[s][i];
            }
        }
        double[][] xi = new double[k][k];
        for (int s = 0; s < t - 1; s++) {
            for (int i = 0; i < k; i++) {
                for (int j = 0; j < k; j++) {
                    xi[i][j] += al[s][i] * a[i][j] * b[s + 1][j] * be[s + 1][j] / c[s + 1];
                }
            }
        }
        return new EStep(ll, g, xi);
    }
}
