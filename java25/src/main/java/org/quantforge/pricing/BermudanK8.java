package org.quantforge.pricing;

import java.util.ArrayList;
import java.util.List;

/**
 * K-8 (stage K; rulings KR-8 and KR-15): the {@code CN_RANNACHER_SMOOTHED} Bermudan scheme, ported from
 * {@code python/quantforge_core/bermudan_k8.py} (specifications/06-risk/bermudan-ladder-k8.md, version 0.2.0). Same
 * state, grid, knots and exercise value as the pinned G-18 scheme, with three changes: the scheme carries
 * {@code U = V exp(-int_0^t alpha)}, so the operator has no curve term and is constant in time; Crank-Nicolson
 * stepping with the first two steps after the maturity payoff and after each exercise date each replaced by two
 * implicit half steps; and the exercise {@code max} applied as a hat-weighted average with an end correction.
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
    }

    // --- the scheme ----------------------------------------------------------------------------------------

    /** {@code u + c} for a dual {@code u} and a constant {@code c}. */
    private static double[] plus(double[] u, double c) {
        double[] o = u.clone();
        o[0] += c;
        return o;
    }

    /** Exercise value at {@code t} times {@code D(t) = exp(-int_0^t alpha)} (spec step 3); no forward rate. */
    private static double[][] exercise(Model m, double t, double[][] xs, double[] times, double k, double phi) {
        List<Double> after = new ArrayList<>();
        for (double s : times) {
            if (s > t) {
                after.add(s);
            }
        }
        int nx = xs.length;
        int w = xs[0].length;
        double[] e1 = expm1(scale(t, neg(m.a)));
        double[] e2 = expm1(scale(t, scale(-2, m.a)));
        double[] bigI = plus(sub(scale(2, div(e1, m.a)), div(e2, scale(2, m.a))), t);
        double[] c2 = div(m.s2, scale(2, mul(m.a, m.a)));
        double[] c4 = div(m.s2, scale(4, m.a));
        double[] lead = exp(sub(m.curve.logDiscount(t), mul(c2, bigI)));
        double[][] fixed = new double[nx][w];
        double[][] last = fixed;
        for (int q = 0; q < after.size(); q++) {
            double s = after.get(q);
            double tau = q == 0 ? s - t : s - after.get(q - 1);
            double[] b = m.bigB(s - t);
            double[] drift = sub(mul(c2, add(bigI, mul(b, mul(e1, e1)))), mul(c4, mul(e2, mul(b, b))));
            double[] head = sub(m.curve.logDiscount(s), drift);
            double[][] p = new double[nx][];
            for (int i = 0; i < nx; i++) {
                p[i] = exp(sub(head, mul(b, xs[i])));
                fixed[i] = add(fixed[i], scale(tau, p[i]));
            }
            last = p;
        }
        double[][] out = new double[nx][];
        for (int i = 0; i < nx; i++) {
            out[i] = scale(phi, sub(sub(lead, last[i]), scale(k, fixed[i])));
        }
        return out;
    }

    /** {@code int_0^1 (1 - u) max(p + (q - p) u, 0) du}: half of the hat-weighted average of the positive part. */
    static double[] hatPart(double[] p, double[] q) {
        double a = p[0];
        double b = q[0];
        if (a >= 0 && b >= 0) {
            return add(divScalar(p, 3), divScalar(q, 6));
        }
        if (a > 0 && b < 0) {
            double[] d = sub(p, q);
            double[] t = div(mul(p, p), scale(2, d));
            return sub(t, divScalar(mul(t, div(p, d)), 3));
        }
        if (a < 0 && b > 0) {
            double[] r = div(q, sub(q, p));
            return divScalar(mul(q, mul(r, r)), 6);
        }
        return new double[p.length];
    }

    /** {@code max(V, E)} at an exercise date as a second-order smoothing (KR-15 b, spec step 5). */
    static double[][] smoothedMax(double[][] v, double[][] e) {
        int n = v.length;
        int w = v[0].length;
        double[][] f = new double[n][];
        for (int i = 0; i < n; i++) {
            f[i] = sub(v[i], e[i]);
        }
        double[][] h = new double[n][];
        double[][] d2 = new double[n][w];
        for (int i = 0; i < n; i++) {
            double[] before = i > 0 ? f[i - 1] : sub(scale(2, f[0]), f[1]);
            double[] after = i < n - 1 ? f[i + 1] : sub(scale(2, f[n - 1]), f[n - 2]);
            h[i] = add(hatPart(f[i], before), hatPart(f[i], after));
            if (i > 0 && i < n - 1) {
                d2[i] = add(sub(f[i - 1], scale(2, f[i])), f[i + 1]);
            }
        }
        for (int j = 0; j < n - 1; j++) {
            double a = f[j][0];
            double b = f[j + 1][0];
            if (!((a > 0 && b < 0) || (a < 0 && b > 0))) {
                continue;
            }
            int pos = a > 0 ? j : j + 1;
            int neg = a > 0 ? j + 1 : j;
            double[] rho = div(f[pos], sub(f[pos], f[neg])); // the part of the cell where V > E
            double[] rest = plus(neg(rho), 1.0);
            double[] g = divScalar(mul(mul(rho, rest), plus(scale(2, rho), -1.0)), 12);
            double[] corr = mul(g, scale(0.5, add(d2[j], d2[j + 1])));
            h[pos] = sub(h[pos], mul(rest, corr));
            h[neg] = sub(h[neg], mul(rho, corr));
        }
        double[][] out = new double[n][];
        for (int i = 0; i < n; i++) {
            double[] o = h[i];
            if (i > 0 && i < n - 1) {
                o = sub(o, divScalar(add(sub(h[i - 1], scale(2, h[i])), h[i + 1]), 6));
            }
            out[i] = add(e[i], o);
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

    /** Rows of {@code A = -L} at the interior nodes, before the boundary substitution; constant in time (KR-15 a). */
    private static final class Operator {
        final double[][] lower;
        final double[][] upper;
        final double[][] diag;

        Operator(Model m, double[][] xs, double[] dx) {
            int n = xs.length - 2;
            double[] diff = div(m.s2, scale(2, mul(dx, dx)));
            double[] twoDx = scale(2, dx);
            lower = new double[n][];
            upper = new double[n][];
            diag = new double[n][];
            for (int i = 0; i < n; i++) {
                double[] inner = xs[i + 1];
                double[] conv = div(mul(m.a, inner), twoDx);
                lower[i] = neg(add(diff, conv));
                upper[i] = neg(sub(diff, conv));
                diag[i] = add(scale(2, diff), inner);
            }
        }
    }

    /** Solves {@code (I + w A) y = rhs} on the interior with linear extrapolation at both ends. */
    private static double[][] implicit(Operator op, double w, double[][] rhs) {
        int n = rhs.length;
        double[][] lower = new double[n][];
        double[][] upper = new double[n][];
        double[][] diag = new double[n][];
        for (int i = 0; i < n; i++) {
            lower[i] = scale(w, op.lower[i]);
            upper[i] = scale(w, op.upper[i]);
            diag[i] = plus(scale(w, op.diag[i]), 1.0);
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

    /** {@code (I - w A) v} at the interior nodes. */
    private static double[][] explicit(Operator op, double w, double[][] v) {
        int n = v.length - 2;
        double[][] out = new double[n][];
        for (int i = 0; i < n; i++) {
            double[] lv = add(add(mul(op.lower[i], v[i]), mul(op.diag[i], v[i + 1])), mul(op.upper[i], v[i + 2]));
            out[i] = sub(v[i + 1], scale(w, lv));
        }
        return out;
    }

    /** Steps replaced by two implicit half steps each after every exercise date (KR-15 c). */
    static final int START_UP_STEPS = 2;

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
            double half = (tHi - tLo) / steps / 2;
            for (long j = steps - 1; j >= 0; j--) {
                if (j >= steps - START_UP_STEPS) { // Rannacher start-up: two implicit half steps
                    v = implicit(op, half, interior(v));
                    v = implicit(op, half, interior(v));
                } else {
                    v = implicit(op, half, explicit(op, half, v));
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
