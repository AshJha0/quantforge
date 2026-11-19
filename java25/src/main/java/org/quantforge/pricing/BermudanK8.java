package org.quantforge.pricing;

import java.util.ArrayList;
import java.util.List;

/**
 * K-8 (stage K wave 1, PROPOSED; ruling KR-8): the {@code CN_RANNACHER_SMOOTHED} Bermudan scheme, ported from
 * {@code python/quantforge_core/bermudan_k8.py}. Same state, grid and exercise value as the pinned G-18 scheme, with
 * Crank-Nicolson stepping (two implicit half steps after the maturity payoff and after each exercise date) and the
 * cell average of {@code max(V, E)} at every exercise date.
 *
 * <p>The ladder is the exact derivative of this discrete scheme in tangent mode: every quantity is a vector whose
 * entry 0 is the value and entries 1.. its derivatives with respect to the log discount factors of the curve nodes,
 * the mean reversion and the volatility (the same deviation from KR-8 step 4's reverse mode as the Python build).
 */
public final class BermudanK8 {
    private BermudanK8() {}

    public static final String METHOD = "CN_RANNACHER_SMOOTHED";

    // --- dual arithmetic: entry 0 is the value, 1.. the tangents ----------------------------------------

    static double[] mul(double[] u, double[] v) {
        double[] o = new double[u.length];
        o[0] = u[0] * v[0];
        for (int c = 1; c < o.length; c++) {
            o[c] = u[0] * v[c] + v[0] * u[c];
        }
        return o;
    }

    static double[] div(double[] u, double[] v) {
        double[] o = new double[u.length];
        double q = u[0] / v[0];
        o[0] = q;
        for (int c = 1; c < o.length; c++) {
            o[c] = (u[c] - q * v[c]) / v[0];
        }
        return o;
    }

    private static double[] func(double[] u, double value, double slope) {
        double[] o = new double[u.length];
        o[0] = value;
        for (int c = 1; c < o.length; c++) {
            o[c] = slope * u[c];
        }
        return o;
    }

    private static double[] exp(double[] u) {
        double e = Math.exp(u[0]);
        return func(u, e, e);
    }

    private static double[] expm1(double[] u) {
        return func(u, Math.expm1(u[0]), Math.exp(u[0]));
    }

    private static double[] sqrt(double[] u) {
        double s = Math.sqrt(u[0]);
        return func(u, s, 0.5 / s);
    }

    static double[] add(double[] u, double[] v) {
        double[] o = new double[u.length];
        for (int c = 0; c < o.length; c++) {
            o[c] = u[c] + v[c];
        }
        return o;
    }

    static double[] sub(double[] u, double[] v) {
        double[] o = new double[u.length];
        for (int c = 0; c < o.length; c++) {
            o[c] = u[c] - v[c];
        }
        return o;
    }

    static double[] scale(double k, double[] u) {
        double[] o = new double[u.length];
        for (int c = 0; c < o.length; c++) {
            o[c] = k * u[c];
        }
        return o;
    }

    private static double[] neg(double[] u) {
        return scale(-1.0, u);
    }

    private static int bisectRight(double[] a, double x) {
        int lo = 0;
        int hi = a.length;
        while (lo < hi) {
            int mid = (lo + hi) >>> 1;
            if (x < a[mid]) {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }
        return lo;
    }

    /** Log-linear curve on dual logs (G-3). */
    private record Curve(double[] nodes, double[][] logs) {
        double[] logDiscount(double t) {
            if (t <= 0) {
                return new double[logs[0].length];
            }
            int j = Math.min(bisectRight(nodes, t) - 1, nodes.length - 2);
            double w = (t - nodes[j]) / (nodes[j + 1] - nodes[j]);
            double[] o = new double[logs[0].length];
            for (int c = 0; c < o.length; c++) {
                o[c] = logs[j][c] + (logs[j + 1][c] - logs[j][c]) * w;
            }
            return o;
        }

        double[] forward(double t) {
            int j = Math.min(Math.max(bisectRight(nodes, t) - 1, 0), nodes.length - 2);
            double[] o = new double[logs[0].length];
            double span = nodes[j + 1] - nodes[j];
            for (int c = 0; c < o.length; c++) {
                o[c] = -(logs[j + 1][c] - logs[j][c]) / span;
            }
            return o;
        }
    }

    private static final class Model {
        final Curve curve;
        final double[] a;
        final double[] s2;

        Model(Curve curve, double[] a, double[] sigma) {
            this.curve = curve;
            this.a = a;
            this.s2 = mul(sigma, sigma);
        }

        double[] bigB(double tau) {
            return neg(div(expm1(scale(tau, neg(a))), a));
        }

        double[] alpha(double t) {
            double[] e = expm1(scale(t, neg(a)));
            return add(curve.forward(t), div(mul(s2, mul(e, e)), scale(2, mul(a, a))));
        }

        double[][] lnA(double t, double s) {
            double[] b = bigB(s - t);
            double[] e2 = expm1(scale(t, scale(-2, a)));
            double[] ln = add(add(sub(curve.logDiscount(s), curve.logDiscount(t)), mul(b, curve.forward(t))),
                    mul(div(s2, scale(4, a)), mul(e2, mul(b, b))));
            return new double[][] {ln, b};
        }
    }

    // --- the scheme ----------------------------------------------------------------------------------------

    private static double[][] exercise(Model m, double t, double[][] xs, double[] times, double k, double phi) {
        List<Double> after = new ArrayList<>();
        for (double s : times) {
            if (s > t) {
                after.add(s);
            }
        }
        int nx = xs.length;
        int w = xs[0].length;
        double[] al = m.alpha(t);
        double[][] r = new double[nx][];
        for (int i = 0; i < nx; i++) {
            r[i] = add(xs[i], al);
        }
        double[][] fixed = new double[nx][w];
        double[][] last = fixed;
        for (int q = 0; q < after.size(); q++) {
            double s = after.get(q);
            double tau = q == 0 ? s - t : s - after.get(q - 1);
            double[][] lb = m.lnA(t, s);
            double[][] p = new double[nx][];
            for (int i = 0; i < nx; i++) {
                p[i] = exp(sub(lb[0], mul(lb[1], r[i])));
                fixed[i] = add(fixed[i], scale(tau, p[i]));
            }
            last = p;
        }
        double[][] out = new double[nx][];
        for (int i = 0; i < nx; i++) {
            double[] o = neg(add(last[i], scale(k, fixed[i])));
            o[0] += 1.0;
            out[i] = scale(phi, o);
        }
        return out;
    }

    /** Mean of {@code max(f, 0)} over a segment where {@code f} is linear from {@code lo} to {@code hi}. */
    private static double[] positiveMean(double[] lo, double[] hi) {
        double a = lo[0];
        double b = hi[0];
        if (a >= 0 && b >= 0) {
            return scale(0.5, add(lo, hi));
        }
        if (a > 0 || b > 0) {
            double[] p = a >= b ? lo : hi;
            double[] q = a >= b ? hi : lo;
            return div(mul(p, p), scale(2, sub(p, q)));
        }
        return new double[lo.length];
    }

    private static double[][][] halves(double[][] g) {
        int n = g.length;
        double[][] left = new double[n][];
        double[][] right = new double[n][];
        for (int i = 1; i < n; i++) {
            left[i] = scale(0.5, add(g[i - 1], g[i]));
        }
        for (int i = 0; i < n - 1; i++) {
            right[i] = left[i + 1];
        }
        left[0] = sub(scale(1.5, g[0]), scale(0.5, g[1]));
        right[n - 1] = sub(scale(1.5, g[n - 1]), scale(0.5, g[n - 2]));
        return new double[][][] {left, right};
    }

    /** Cell average of {@code max(V, E)} at every node (KR-8 step 3). */
    static double[][] smoothedMax(double[][] v, double[][] e) {
        int n = v.length;
        double[][] f = new double[n][];
        for (int i = 0; i < n; i++) {
            f[i] = sub(v[i], e[i]);
        }
        double[][][] fh = halves(f);
        double[][][] eh = halves(e);
        double[][] out = new double[n][];
        for (int i = 0; i < n; i++) {
            double[] eMean = scale(0.25, add(add(eh[0][i], scale(2, e[i])), eh[1][i]));
            out[i] = add(eMean, scale(0.5, add(positiveMean(fh[0][i], f[i]), positiveMean(f[i], fh[1][i]))));
        }
        return out;
    }

    /** Value-only elimination, then every column with the same multipliers and pivots; returns rows x columns. */
    private static double[][] solve(double[][] lower, double[][] diag, double[][] upper, double[][] rhs) {
        int n = diag.length;
        int w = rhs[0].length;
        double[] c = new double[n];
        double[] den = new double[n];
        den[0] = diag[0][0];
        c[0] = upper[0][0] / den[0];
        for (int i = 1; i < n; i++) {
            den[i] = diag[i][0] - lower[i][0] * c[i - 1];
            c[i] = upper[i][0] / den[i];
        }
        double[] y0 = new double[n];
        y0[0] = rhs[0][0] / den[0];
        for (int i = 1; i < n; i++) {
            y0[i] = (rhs[i][0] - lower[i][0] * y0[i - 1]) / den[i];
        }
        for (int i = n - 2; i >= 0; i--) {
            y0[i] -= c[i] * y0[i + 1];
        }
        double[][] full = new double[n][];
        for (int i = 0; i < n; i++) {
            full[i] = rhs[i].clone();
            for (int k = 1; k < w; k++) {
                full[i][k] -= diag[i][k] * y0[i];
            }
        }
        for (int i = 1; i < n; i++) {
            for (int k = 1; k < w; k++) {
                full[i][k] -= lower[i][k] * y0[i - 1];
            }
        }
        for (int i = 0; i < n - 1; i++) {
            for (int k = 1; k < w; k++) {
                full[i][k] -= upper[i][k] * y0[i + 1];
            }
        }
        double[][] d = new double[n][w];
        for (int k = 1; k < w; k++) {
            d[0][k] = full[0][k] / den[0];
        }
        for (int i = 1; i < n; i++) {
            for (int k = 1; k < w; k++) {
                d[i][k] = (full[i][k] - lower[i][0] * d[i - 1][k]) / den[i];
            }
        }
        for (int i = n - 2; i >= 0; i--) {
            for (int k = 1; k < w; k++) {
                d[i][k] -= c[i] * d[i + 1][k];
            }
        }
        for (int i = 0; i < n; i++) {
            d[i][0] = y0[i];
        }
        return d;
    }

    /** Rows of {@code L} at the interior nodes, before the boundary substitution. */
    private static final class Operator {
        final Model m;
        final double[][] lower;
        final double[][] upper;
        final double[][] base;

        Operator(Model m, double[][] xs, double[] dx) {
            int n = xs.length - 2;
            double[] diff = div(m.s2, scale(2, mul(dx, dx)));
            double[] twoDx = scale(2, dx);
            this.m = m;
            lower = new double[n][];
            upper = new double[n][];
            base = new double[n][];
            for (int i = 0; i < n; i++) {
                double[] inner = xs[i + 1];
                double[] conv = div(mul(m.a, inner), twoDx);
                lower[i] = neg(add(diff, conv));
                upper[i] = neg(sub(diff, conv));
                base[i] = add(scale(2, diff), inner);
            }
        }

        double[][] diag(double t) {
            double[] al = m.alpha(t);
            double[][] o = new double[base.length][];
            for (int i = 0; i < o.length; i++) {
                o[i] = add(base[i], al);
            }
            return o;
        }
    }

    /** Solves {@code (I + w L(t)) y = rhs} on the interior with linear extrapolation at both ends. */
    private static double[][] implicit(Operator op, double t, double w, double[][] rhs) {
        int n = rhs.length;
        double[][] lower = new double[n][];
        double[][] upper = new double[n][];
        double[][] diag = op.diag(t);
        for (int i = 0; i < n; i++) {
            lower[i] = scale(w, op.lower[i]);
            upper[i] = scale(w, op.upper[i]);
            diag[i] = scale(w, diag[i]);
            diag[i][0] += 1.0;
        }
        diag[0] = add(diag[0], scale(2, lower[0]));
        upper[0] = sub(upper[0], lower[0]);
        lower[n - 1] = sub(lower[n - 1], upper[n - 1]);
        diag[n - 1] = add(diag[n - 1], scale(2, upper[n - 1]));
        double[][] y = solve(lower, diag, upper, rhs);
        double[][] out = new double[n + 2][];
        out[0] = sub(scale(2, y[0]), y[1]);
        System.arraycopy(y, 0, out, 1, n);
        out[n + 1] = sub(scale(2, y[n - 1]), y[n - 2]);
        return out;
    }

    /** {@code (I - w L(t)) v} at the interior nodes. */
    private static double[][] explicit(Operator op, double t, double w, double[][] v) {
        int n = v.length - 2;
        double[][] diag = op.diag(t);
        double[][] out = new double[n][];
        for (int i = 0; i < n; i++) {
            double[] lv = add(add(mul(op.lower[i], v[i]), mul(diag[i], v[i + 1])), mul(op.upper[i], v[i + 2]));
            out[i] = sub(v[i + 1], scale(w, lv));
        }
        return out;
    }

    private static double[][] interior(double[][] v) {
        double[][] o = new double[v.length - 2][];
        System.arraycopy(v, 1, o, 0, o.length);
        return o;
    }

    /**
     * Price per unit notional (entry 0) and, with {@code tangents}, its derivatives with respect to the log discount
     * factors of the curve pillars, {@code a} and {@code sigma} (entries 1..).
     */
    public static double[] scheme(double[] times, double[] dfs, double a, double sigma, double[] paymentTimes,
            double k, boolean payer, double[] exerciseTimes, int nx, long stepsPerYear, double width,
            boolean tangents) {
        int n = times.length;
        int w = tangents ? n + 3 : 1;
        double[][] logs = new double[n + 1][w];
        for (int j = 0; j < n; j++) {
            logs[j + 1][0] = Math.log(dfs[j]);
        }
        double[] ad = new double[w];
        double[] sd = new double[w];
        ad[0] = a;
        sd[0] = sigma;
        if (tangents) {
            for (int j = 0; j < n; j++) {
                logs[j + 1][j + 1] = 1.0;
            }
            ad[n + 1] = 1.0;
            sd[n + 2] = 1.0;
        }
        double[] nodes = new double[n + 1];
        System.arraycopy(times, 0, nodes, 1, n);
        Model m = new Model(new Curve(nodes, logs), ad, sd);
        double phi = payer ? 1.0 : -1.0;
        double tm = exerciseTimes[exerciseTimes.length - 1];
        double[] g = neg(div(expm1(scale(-2 * tm, ad)), scale(2, ad)));
        double[] sx = mul(sd, sqrt(g));
        double[] h = scale(width, sx);
        double[] dx = divScalar(scale(2, h), nx - 1);
        double[][] xs = new double[nx][];
        for (int i = 0; i < nx; i++) {
            xs[i] = add(neg(h), scale(i, dx));
        }
        Operator op = new Operator(m, xs, dx);
        double[][] v = smoothedMax(new double[nx][w], exercise(m, tm, xs, paymentTimes, k, phi));
        double[] grid = new double[exerciseTimes.length + 1];
        System.arraycopy(exerciseTimes, 0, grid, 1, exerciseTimes.length);
        for (int kk = grid.length - 1; kk > 0; kk--) {
            double tHi = grid[kk];
            double tLo = grid[kk - 1];
            long steps = Math.max(1, (long) Math.ceil(stepsPerYear * (tHi - tLo)));
            double dt = (tHi - tLo) / steps;
            for (long j = steps - 1; j >= 0; j--) {
                double t = tLo + j * dt;
                if (j == steps - 1) { // Rannacher start-up: two implicit half steps
                    double mid = t + dt / 2;
                    v = implicit(op, mid, dt / 2, interior(v));
                    v = implicit(op, t, dt / 2, interior(v));
                } else {
                    v = implicit(op, t, dt / 2, explicit(op, tLo + (j + 1) * dt, dt / 2, v));
                }
            }
            if (kk - 1 > 0) {
                v = smoothedMax(v, exercise(m, tLo, xs, paymentTimes, k, phi));
            }
        }
        return v[nx / 2];
    }

    private static double[] divScalar(double[] u, double d) {
        double[] o = new double[u.length];
        for (int c = 0; c < o.length; c++) {
            o[c] = u[c] / d;
        }
        return o;
    }

    /** {@code rates.shortrate.bermudan_swaption} with {@code method} {@code CN_RANNACHER_SMOOTHED}; inputs checked. */
    public static double price(double[] times, double[] dfs, double a, double sigma, double[] pay, double rate,
            boolean payer, double notional, double[] exercise, ShortRateFd.Grid g) {
        double[] r = scheme(times, dfs, a, sigma, pay, rate, payer, exercise, g.nx(), g.stepsPerYear(), g.width(),
                false);
        return notional * r[0];
    }

    /** {@code rates.shortrate.bermudan_ladder} with {@code method} {@code CN_RANNACHER_SMOOTHED}; inputs checked. */
    public static BermudanLadder.Ladder ladder(double[] times, double[] dfs, double a, double sigma, double[] pay,
            double rate, boolean payer, double notional, double[] exercise, ShortRateFd.Grid g) {
        double[] r = scheme(times, dfs, a, sigma, pay, rate, payer, exercise, g.nx(), g.stepsPerYear(), g.width(),
                true);
        int n = times.length;
        double[] d = new double[n];
        for (int j = 0; j < n; j++) {
            d[j] = notional * r[1 + j] / dfs[j];
        }
        return new BermudanLadder.Ladder(notional * r[0], d, notional * r[n + 1], notional * r[n + 2]);
    }
}
