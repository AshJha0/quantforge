package org.quantforge.calibration;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;

/** Regularised and outlier-robust curve fits (curve-fits.md). */
public final class CurveFits {
    private CurveFits() {}

    public record Smooth(double[] forwards, double[] fitted, double objective) {}

    public static Smooth smooth(double[] knots, double[] m, double[] y, double lambda, double[] w) {
        if (m.length != y.length || (w != null && w.length != m.length) || m.length == 0) {
            throw new QfError("E_INPUT", "maturities, zero_rates and weights need one equal, non-zero length");
        }
        if (knots.length == 0) {
            throw new QfError("E_INPUT", "no knots", "knots");
        }
        double previous = 0.0;
        for (double k : knots) {
            if (!(k > previous)) {
                throw new QfError("E_INPUT", "knots must be positive and strictly increasing", "knots");
            }
            previous = k;
        }
        if (!(lambda >= 0.0)) {
            throw new QfError("E_DOMAIN", "lambda must not be negative", "lambda");
        }
        if (w != null) {
            for (double v : w) {
                if (!(v >= 0.0)) {
                    throw new QfError("E_DOMAIN", "weights must not be negative", "weights");
                }
            }
        }
        for (double v : m) {
            if (!(v > 0.0)) {
                throw new QfError("E_DOMAIN", "maturities must be positive", "maturities");
            }
        }
        int n = knots.length;
        for (double v : m) {
            if (v > knots[n - 1]) {
                throw new QfError("E_INPUT", "maturity past the last knot", "maturities");
            }
        }
        double[][] b = new double[m.length][n];
        for (int j = 0; j < m.length; j++) {
            double lo = 0.0;
            for (int k = 0; k < n; k++) {
                double len = Math.min(knots[k], m[j]) - lo;
                b[j][k] = len > 0.0 ? len / m[j] : 0.0;
                lo = knots[k];
            }
        }
        double[][] a = new double[n][n];
        double[] rhs = new double[n];
        for (int j = 0; j < m.length; j++) {
            double wj = w == null ? 1.0 : w[j];
            for (int r = 0; r < n; r++) {
                rhs[r] += b[j][r] * wj * y[j];
                for (int c = 0; c < n; c++) {
                    a[r][c] += b[j][r] * wj * b[j][c];
                }
            }
        }
        for (int k = 0; k + 1 < n; k++) {
            a[k][k] += lambda;
            a[k + 1][k + 1] += lambda;
            a[k][k + 1] -= lambda;
            a[k + 1][k] -= lambda;
        }
        double[] f = LinearAlgebra.solve(a, rhs);
        double[] fitted = new double[m.length];
        double obj = 0.0;
        for (int j = 0; j < m.length; j++) {
            for (int k = 0; k < n; k++) {
                fitted[j] += b[j][k] * f[k];
            }
            double r = fitted[j] - y[j];
            obj += (w == null ? 1.0 : w[j]) * r * r;
        }
        for (int k = 0; k + 1 < n; k++) {
            obj += lambda * (f[k + 1] - f[k]) * (f[k + 1] - f[k]);
        }
        return new Smooth(f, fitted, obj);
    }

    public record Robust(double[] betas, double[] residuals, int[] outliers, double objective) {}

    public static Robust robust(double[] m, double[] y, double tau, double delta) {
        if (m.length != y.length || m.length < 3) {
            throw new QfError("E_INPUT", "need at least 3 points of equal length");
        }
        if (!(tau > 0.0) || !(delta > 0.0)) {
            throw new QfError("E_DOMAIN", "tau and delta must be positive");
        }
        for (double v : m) {
            if (!(v > 0.0)) {
                throw new QfError("E_DOMAIN", "maturities must be positive", "maturities");
            }
        }
        int n = m.length;
        double[][] x = new double[n][3];
        for (int j = 0; j < n; j++) {
            double u = m[j] / tau;
            double e = -Math.expm1(-u) / u;
            x[j][0] = 1.0;
            x[j][1] = e;
            x[j][2] = e - Math.exp(-u);
        }
        double[] beta = weighted(x, y, new double[n], delta, null);
        double obj = objective(x, y, beta, delta);
        for (int it = 0; it < 500; it++) {
            double[] r = residuals(x, y, beta);
            double[] next = newton(x, y, r, delta);
            if (next == null) {
                next = irls(x, y, r, delta);
            }
            double[] p = new double[3];
            for (int i = 0; i < 3; i++) {
                p[i] = next[i] - beta[i];
            }
            double step = 1.0;
            double[] trial = beta;
            double trialObj = obj;
            for (int h = 0; h < 60; h++) {
                double[] cand = {beta[0] + step * p[0], beta[1] + step * p[1], beta[2] + step * p[2]};
                double co = objective(x, y, cand, delta);
                if (co <= obj) {
                    trial = cand;
                    trialObj = co;
                    break;
                }
                step /= 2.0;
            }
            boolean same = trial[0] == beta[0] && trial[1] == beta[1] && trial[2] == beta[2];
            beta = trial;
            obj = trialObj;
            if (same) {
                break;
            }
        }
        double[] r = residuals(x, y, beta);
        List<Integer> out = new ArrayList<>();
        for (int j = 0; j < n; j++) {
            if (Math.abs(r[j]) > delta) {
                out.add(j);
            }
        }
        return new Robust(beta, r, out.stream().mapToInt(Integer::intValue).toArray(), obj);
    }

    private static double[] residuals(double[][] x, double[] y, double[] b) {
        double[] r = new double[y.length];
        for (int j = 0; j < y.length; j++) {
            r[j] = b[0] * x[j][0] + b[1] * x[j][1] + b[2] * x[j][2] - y[j];
        }
        return r;
    }

    private static double objective(double[][] x, double[] y, double[] b, double delta) {
        double s = 0.0;
        for (double r : residuals(x, y, b)) {
            double a = Math.abs(r);
            s += a <= delta ? r * r / 2.0 : delta * a - delta * delta / 2.0;
        }
        return s;
    }

    /** The exact minimiser for the inlier set and outlier signs that {@code r} implies; null if singular. */
    private static double[] newton(double[][] x, double[] y, double[] r, double delta) {
        double[] sign = new double[y.length];
        for (int j = 0; j < y.length; j++) {
            sign[j] = Math.abs(r[j]) <= delta ? 0.0 : Math.signum(r[j]);
        }
        try {
            return weighted(x, y, sign, delta, null);
        } catch (QfError e) {
            return null;
        }
    }

    /** One reweighted least-squares step, for when too few inliers remain for {@link #newton}. */
    private static double[] irls(double[][] x, double[] y, double[] r, double delta) {
        double[] w = new double[y.length];
        for (int j = 0; j < y.length; j++) {
            w[j] = Math.abs(r[j]) <= delta ? 1.0 : delta / Math.abs(r[j]);
        }
        return weighted(x, y, new double[y.length], delta, w);
    }

    /**
     * Solves sum over inliers of x_j (x_j b - y_j) w_j + delta sum over outliers of s_j x_j = 0. Point j is an
     * outlier when {@code sign[j] != 0}; {@code w} null means unit weights.
     */
    private static double[] weighted(double[][] x, double[] y, double[] sign, double delta, double[] w) {
        double[][] a = new double[3][3];
        double[] rhs = new double[3];
        for (int j = 0; j < y.length; j++) {
            if (sign[j] != 0.0) {
                for (int r = 0; r < 3; r++) {
                    rhs[r] -= delta * sign[j] * x[j][r];
                }
                continue;
            }
            double wj = w == null ? 1.0 : w[j];
            for (int r = 0; r < 3; r++) {
                rhs[r] += wj * x[j][r] * y[j];
                for (int c = 0; c < 3; c++) {
                    a[r][c] += wj * x[j][r] * x[j][c];
                }
            }
        }
        return LinearAlgebra.solve(a, rhs);
    }
}
