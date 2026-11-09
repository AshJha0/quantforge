package org.quantforge.calibration;

import org.quantforge.core.Finite;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;

/** Weighted, regularised least squares (least-squares.md). Judged on the objective, never on the path. */
public final class LeastSquares {
    private LeastSquares() {}

    public enum Model {
        LINEAR(2), EXPONENTIAL(2), NELSON_SIEGEL(4), ROSENBROCK(2);

        final int size;

        Model(int size) {
            this.size = size;
        }
    }

    public enum Method { GAUSS_NEWTON, LEVENBERG_MARQUARDT, BFGS }

    /** Optional fields are null when absent. */
    public record Problem(Model model, double[] x, double[] y, double[] start, Method method, double[] weights,
                          double regularisation, double[] prior, double[] lower, double[] upper, long maxIter) {}

    public record Fit(double[] parameters, double objective, int iterations, String status, double[] residuals) {}

    public record Breach(int index, String side, double distance) {}

    private static final double GRADIENT_TOL = 1e-8;
    private static final double STEP_TOL = 1e-12;

    /** Residuals r and Jacobian J, so that the objective is |r|^2. */
    private record Linearised(double[] r, double[][] jac) {
        double objective() {
            double s = 0.0;
            for (double v : r) {
                s += v * v;
            }
            return s;
        }

        double[] gradient() {
            int n = jac[0].length;
            double[] g = new double[n];
            for (int i = 0; i < r.length; i++) {
                for (int k = 0; k < n; k++) {
                    g[k] += 2.0 * jac[i][k] * r[i];
                }
            }
            return g;
        }

        double[][] normal() {
            int n = jac[0].length;
            double[][] a = new double[n][n];
            for (double[] row : jac) {
                for (int p = 0; p < n; p++) {
                    for (int q = 0; q < n; q++) {
                        a[p][q] += row[p] * row[q];
                    }
                }
            }
            return a;
        }
    }

    private static double model(Model m, double x, double[] p) {
        return switch (m) {
            case LINEAR -> p[0] + p[1] * x;
            case EXPONENTIAL -> p[0] * Math.exp(-p[1] * x);
            case NELSON_SIEGEL -> {
                double u = x / p[3];
                double ex = Math.exp(-u);
                double e = u == 0.0 ? 1.0 : (1.0 - ex) / u;
                yield p[0] + p[1] * e + p[2] * (e - ex);
            }
            case ROSENBROCK -> throw new IllegalArgumentException();
        };
    }

    private static double[] modelGradient(Model m, double x, double[] p) {
        return switch (m) {
            case LINEAR -> new double[] {1.0, x};
            case EXPONENTIAL -> {
                double e = Math.exp(-p[1] * x);
                yield new double[] {e, -p[0] * x * e};
            }
            case NELSON_SIEGEL -> {
                double u = x / p[3];
                double ex = Math.exp(-u);
                double e = u == 0.0 ? 1.0 : (1.0 - ex) / u;
                double de = u == 0.0 ? -0.5 : (ex * (u + 1.0) - 1.0) / (u * u);
                double dp3 = (p[1] * de + p[2] * (de + ex)) * (-u / p[3]);
                yield new double[] {1.0, e, e - ex, dp3};
            }
            case ROSENBROCK -> throw new IllegalArgumentException();
        };
    }

    private static Linearised linearise(Problem q, double[] p) {
        int n = p.length;
        List<double[]> rows = new ArrayList<>();
        List<Double> res = new ArrayList<>();
        if (q.model() == Model.ROSENBROCK) {
            res.add(1.0 - p[0]);
            rows.add(new double[] {-1.0, 0.0});
            res.add(10.0 * (p[1] - p[0] * p[0]));
            rows.add(new double[] {-20.0 * p[0], 10.0});
        } else {
            for (int i = 0; i < q.x().length; i++) {
                double w = q.weights() == null ? 1.0 : Math.sqrt(q.weights()[i]);
                res.add(w * (model(q.model(), q.x()[i], p) - q.y()[i]));
                double[] g = modelGradient(q.model(), q.x()[i], p);
                for (int k = 0; k < n; k++) {
                    g[k] *= w;
                }
                rows.add(g);
            }
        }
        if (q.regularisation() > 0.0) {
            double s = Math.sqrt(q.regularisation());
            for (int k = 0; k < n; k++) {
                res.add(s * (p[k] - (q.prior() == null ? 0.0 : q.prior()[k])));
                double[] row = new double[n];
                row[k] = s;
                rows.add(row);
            }
        }
        if (rows.isEmpty()) {
            rows.add(new double[n]);
            res.add(0.0);
        }
        double[] r = new double[res.size()];
        for (int i = 0; i < r.length; i++) {
            r[i] = res.get(i);
        }
        return new Linearised(r, rows.toArray(new double[0][]));
    }

    private static double norm(double[] v) {
        double s = 0.0;
        for (double e : v) {
            s += e * e;
        }
        return Math.sqrt(s);
    }

    private static boolean smallStep(double[] step, double[] p) {
        return norm(step) <= STEP_TOL * (1.0 + norm(p));
    }

    private static double[] plus(double[] p, double[] d, double scale) {
        double[] out = p.clone();
        for (int i = 0; i < out.length; i++) {
            out[i] += scale * d[i];
        }
        return out;
    }

    private static QfError exhausted() {
        return new QfError("E_NO_CONVERGENCE", "max_iter reached");
    }

    private static void check(Problem q) {
        if (q.x().length != q.y().length) {
            throw new QfError("E_INPUT", "x and y differ in length");
        }
        int n = q.model().size;
        if (q.start().length != n) {
            throw new QfError("E_INPUT", "start has the wrong length", "start");
        }
        boolean weighted = q.weights() != null && q.model() != Model.ROSENBROCK; // Weights do not apply to it.
        if (weighted && q.weights().length != q.x().length) {
            throw new QfError("E_INPUT", "weights have the wrong length", "weights");
        }
        if (q.maxIter() < 1) {
            throw new QfError("E_INPUT", "max_iter must be at least 1", "max_iter");
        }
        if (q.prior() != null && q.prior().length != n) {
            throw new QfError("E_INPUT", "prior has the wrong length", "prior");
        }
        boolean bounded = q.lower() != null || q.upper() != null;
        if (bounded && q.method() != Method.LEVENBERG_MARQUARDT) {
            throw new QfError("E_INPUT", "bounds need LEVENBERG_MARQUARDT");
        }
        for (double[] b : new double[][] {q.lower(), q.upper()}) {
            if (b != null && b.length != n) {
                throw new QfError("E_INPUT", "bounds have the wrong length");
            }
        }
        if (q.lower() != null && q.upper() != null) {
            for (int i = 0; i < n; i++) {
                if (q.lower()[i] > q.upper()[i]) {
                    throw new QfError("E_INPUT", "lower is above upper");
                }
            }
        }
        if (weighted) {
            for (double w : q.weights()) {
                if (w < 0.0) {
                    throw new QfError("E_DOMAIN", "negative weight", "weights");
                }
            }
        }
        if (q.regularisation() < 0.0) {
            throw new QfError("E_DOMAIN", "regularisation is negative", "regularisation");
        }
    }

    public static Fit fit(Problem q) {
        check(q);
        return switch (q.method()) {
            case GAUSS_NEWTON -> gaussNewton(q);
            case LEVENBERG_MARQUARDT -> levenbergMarquardt(q);
            case BFGS -> bfgs(q);
        };
    }

    /** Every method starts from here: an objective or gradient that has overflowed gives no descent to follow. */
    private static Linearised finite(Linearised s) {
        boolean ok = Double.isFinite(s.objective());
        for (double g : s.gradient()) {
            ok &= Double.isFinite(g);
        }
        if (!ok) {
            throw new QfError("E_NON_FINITE", "objective or gradient is not finite");
        }
        return s;
    }

    /**
     * Backtracking ended. With finite trials the step shrank below the step test at rounding level, which is a stop.
     * If every trial was non-finite no acceptable step exists (B22).
     */
    private static Fit stalled(Problem q, double[] p, int iterations, boolean finiteTrial) {
        if (!finiteTrial) {
            throw new QfError("E_NO_CONVERGENCE", "no acceptable step");
        }
        return finish(q, p, iterations, "STEP");
    }

    private static Fit finish(Problem q, double[] p, int iterations, String status) {
        double objective = linearise(q, p).objective();
        double[] residuals = new double[q.x().length];
        if (q.model() != Model.ROSENBROCK) {
            for (int i = 0; i < residuals.length; i++) {
                residuals[i] = model(q.model(), q.x()[i], p) - q.y()[i];
            }
        }
        return new Fit(p, objective, iterations, status, residuals);
    }

    private static Fit gaussNewton(Problem q) {
        double[] p = q.start().clone();
        for (int it = 0; ; it++) {
            Linearised s = finite(linearise(q, p));
            double[] g = s.gradient();
            if (norm(g) <= GRADIENT_TOL) {
                return finish(q, p, it, "GRADIENT");
            }
            if (it >= q.maxIter()) {
                throw exhausted();
            }
            double[] rhs = new double[g.length];
            for (int i = 0; i < g.length; i++) {
                rhs[i] = -g[i] / 2.0;
            }
            double[] step = LinearAlgebra.solve(s.normal(), rhs);
            double scale = 1.0;
            double f0 = s.objective();
            boolean finiteTrial = false;
            while (scale > 1e-20) {
                double trial = linearise(q, plus(p, step, scale)).objective();
                finiteTrial |= Double.isFinite(trial);
                if (trial < f0) {
                    break;
                }
                scale /= 2.0;
            }
            if (scale <= 1e-20) {
                return stalled(q, p, it, finiteTrial);
            }
            double[] next = plus(p, step, scale);
            double[] moved = plus(next, p, -1.0);
            p = next;
            if (smallStep(moved, p)) {
                return finish(q, p, it + 1, "STEP");
            }
        }
    }

    private static double clamp(Problem q, int i, double v) {
        if (q.lower() != null) {
            v = Math.max(v, q.lower()[i]);
        }
        if (q.upper() != null) {
            v = Math.min(v, q.upper()[i]);
        }
        return v;
    }

    private static Fit levenbergMarquardt(Problem q) {
        int n = q.start().length;
        double[] p = new double[n];
        for (int i = 0; i < n; i++) {
            p[i] = clamp(q, i, q.start()[i]);
        }
        double mu = 1e-3;
        Linearised s = finite(linearise(q, p));
        double f0 = s.objective();
        for (int it = 0; ; it++) {
            double[] g = finite(s).gradient();
            double[] projected = new double[n];
            int[] index = new int[n];
            int count = 0;
            for (int i = 0; i < n; i++) {
                projected[i] = p[i] - clamp(q, i, p[i] - g[i]);
                if (clamp(q, i, p[i] - Math.signum(g[i])) != p[i]) {
                    index[count++] = i; // Free: the descent direction is not blocked by a bound.
                }
            }
            if (norm(projected) <= GRADIENT_TOL || count == 0) {
                return finish(q, p, it, "GRADIENT");
            }
            if (it >= q.maxIter()) {
                throw exhausted();
            }
            double[][] a = s.normal();
            double[][] m = new double[count][count];
            double[] rhs = new double[count];
            for (int r = 0; r < count; r++) {
                for (int c = 0; c < count; c++) {
                    m[r][c] = a[index[r]][index[c]];
                }
                m[r][r] += mu * Math.max(a[index[r]][index[r]], 1e-12);
                rhs[r] = -g[index[r]] / 2.0;
            }
            double[] delta;
            try {
                delta = LinearAlgebra.solve(m, rhs);
            } catch (QfError e) {
                mu *= 4.0;
                continue;
            }
            double[] next = p.clone();
            for (int r = 0; r < count; r++) {
                next[index[r]] = clamp(q, index[r], p[index[r]] + delta[r]);
            }
            double[] moved = plus(next, p, -1.0);
            Linearised t = linearise(q, next);
            double f1 = t.objective();
            if (f1 < f0) {
                p = next;
                s = t;
                f0 = f1;
                mu = Math.max(mu / 3.0, 1e-15);
            } else {
                mu *= 4.0;
            }
            if (smallStep(moved, p)) {
                return finish(q, p, it + 1, "STEP");
            }
        }
    }

    private static Fit bfgs(Problem q) {
        int n = q.start().length;
        double[] p = q.start().clone();
        double[][] h = identity(n);
        Linearised s = finite(linearise(q, p));
        double f = s.objective();
        double[] g = s.gradient();
        boolean fresh = true;
        for (int it = 0; ; it++) {
            if (norm(g) <= GRADIENT_TOL) {
                return finish(q, p, it, "GRADIENT");
            }
            if (it >= q.maxIter()) {
                throw exhausted();
            }
            double[] d = new double[n];
            for (int i = 0; i < n; i++) {
                d[i] = -dot(h[i], g);
            }
            double slope = dot(g, d);
            double step = 1.0;
            double[] next = null;
            double fNext = 0.0;
            boolean finiteTrial = false;
            while (slope < 0.0 && step > 1e-20) {
                next = plus(p, d, step);
                fNext = linearise(q, next).objective();
                finiteTrial |= Double.isFinite(fNext);
                if (fNext <= f + 1e-4 * step * slope) {
                    break;
                }
                step /= 2.0;
            }
            if (!(slope < 0.0) || step <= 1e-20) {
                if (fresh) {
                    return stalled(q, p, it, finiteTrial);
                }
                h = identity(n);
                fresh = true;
                continue;
            }
            double[] move = plus(next, p, -1.0);
            double[] gNext = finite(linearise(q, next)).gradient();
            double[] y = plus(gNext, g, -1.0);
            double sy = dot(move, y);
            if (sy > 1e-14 * norm(move) * norm(y)) {
                if (fresh) {
                    double scale = sy / dot(y, y);
                    for (int i = 0; i < n; i++) {
                        h[i][i] = scale;
                    }
                }
                h = update(h, move, y, sy);
                fresh = false;
            }
            p = next;
            f = fNext;
            g = gNext;
            if (smallStep(move, p)) {
                return finish(q, p, it + 1, "STEP");
            }
        }
    }

    private static double dot(double[] a, double[] b) {
        double s = 0.0;
        for (int i = 0; i < a.length; i++) {
            s += a[i] * b[i];
        }
        return s;
    }

    private static double[][] identity(int n) {
        double[][] m = new double[n][n];
        for (int i = 0; i < n; i++) {
            m[i][i] = 1.0;
        }
        return m;
    }

    private static double[][] update(double[][] h, double[] s, double[] y, double sy) {
        int n = s.length;
        double[] hy = new double[n];
        for (int i = 0; i < n; i++) {
            hy[i] = dot(h[i], y);
        }
        double yhy = dot(y, hy);
        double[][] out = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int k = 0; k < n; k++) {
                out[i][k] = h[i][k] + (1.0 + yhy / sy) * s[i] * s[k] / sy - (hy[i] * s[k] + s[i] * hy[k]) / sy;
            }
        }
        return out;
    }

    public static List<Breach> checkBidAsk(double[] fitted, double[] bid, double[] ask) {
        Finite.check("fitted", fitted);
        Finite.check("bid", bid);
        Finite.check("ask", ask);
        if (fitted.length != bid.length || fitted.length != ask.length) {
            throw new QfError("E_INPUT", "lengths differ");
        }
        for (int i = 0; i < bid.length; i++) {
            if (bid[i] > ask[i]) {
                throw new QfError("E_INPUT", "bid is above ask");
            }
        }
        List<Breach> out = new ArrayList<>();
        for (int i = 0; i < fitted.length; i++) {
            if (fitted[i] < bid[i]) {
                out.add(new Breach(i, "BID", bid[i] - fitted[i]));
            } else if (fitted[i] > ask[i]) {
                out.add(new Breach(i, "ASK", fitted[i] - ask[i]));
            }
        }
        return out;
    }
}
