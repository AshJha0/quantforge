package org.quantforge.calibration;

import org.quantforge.core.Finite;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;

/** Regularised and outlier-robust curve fits (curve-fits.md). */
public final class CurveFits {
    private CurveFits() {}

    public record Smooth(double[] forwards, double[] fitted, double objective) {}

    public static Smooth smooth(double[] knots, double[] m, double[] y, double lambda, double[] w) {
        Finite.check("knots", knots);
        Finite.check("m", m);
        Finite.check("y", y);
        Finite.check("lambda", lambda);
        Finite.check("w", w);
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

    /** Ruling D38b: below this reciprocal condition number the robust fit's basis is singular. */
    static final double RCOND_MIN = 1e-12;

    /**
     * Ruling D38b: reciprocal 1-norm condition number of X^T X with columns scaled to unit diagonal, from the
     * explicit 3x3 inverse (adjugate over determinant), in the same operation order as the other languages.
     * 0 when the determinant is not positive.
     */
    static double basisRcond(double[][] x) {
        double[][] g = new double[3][3];
        for (double[] row : x) {
            for (int p = 0; p < 3; p++) {
                for (int q = 0; q < 3; q++) {
                    g[p][q] += row[p] * row[q];
                }
            }
        }
        double[] s = new double[3];
        for (int p = 0; p < 3; p++) {
            s[p] = 1.0 / Math.sqrt(g[p][p]);
        }
        double[][] a = new double[3][3];
        for (int p = 0; p < 3; p++) {
            for (int q = 0; q < 3; q++) {
                a[p][q] = g[p][q] * s[p] * s[q];
            }
        }
        double[][] c = {
            {a[1][1] * a[2][2] - a[1][2] * a[2][1], a[1][2] * a[2][0] - a[1][0] * a[2][2],
                a[1][0] * a[2][1] - a[1][1] * a[2][0]},
            {a[0][2] * a[2][1] - a[0][1] * a[2][2], a[0][0] * a[2][2] - a[0][2] * a[2][0],
                a[0][1] * a[2][0] - a[0][0] * a[2][1]},
            {a[0][1] * a[1][2] - a[0][2] * a[1][1], a[0][2] * a[1][0] - a[0][0] * a[1][2],
                a[0][0] * a[1][1] - a[0][1] * a[1][0]},
        };
        double det = a[0][0] * c[0][0] + a[0][1] * c[0][1] + a[0][2] * c[0][2];
        if (!(det > 0.0)) {
            return 0.0;
        }
        double normA = 0.0;
        double normInv = 0.0;
        for (int q = 0; q < 3; q++) {
            normA = Math.max(normA, Math.abs(a[0][q]) + Math.abs(a[1][q]) + Math.abs(a[2][q]));
            normInv = Math.max(normInv, (Math.abs(c[q][0]) + Math.abs(c[q][1]) + Math.abs(c[q][2])) / det);
        }
        return 1.0 / (normA * normInv);
    }

    /** Working-set changes allowed before {@code robust} gives up (never reached at full rank). */
    private static final int ROBUST_ITERATIONS = 1000;

    public static Robust robust(double[] m, double[] y, double tau, double delta) {
        Finite.check("m", m);
        Finite.check("y", y);
        Finite.check("tau", tau);
        Finite.check("delta", delta);
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
        if (!(basisRcond(x) >= RCOND_MIN)) {
            throw new QfError("E_SINGULAR", "the Nelson-Siegel basis is singular to working precision (D38b)");
        }
        // Primal active-set method on the dual (Nocedal and Wright, algorithm 16.3); the Python
        // implementation carries the full derivation. theta is the dual point, bound[j] the sign
        // s_j of a theta_j held at s_j delta (0 when free); the betas solve the inlier/outlier
        // normal equations of the current working set.
        double[] theta = new double[n];
        double[] bound = new double[n];
        double[] beta = null;
        for (int it = 0; it < ROBUST_ITERATIONS && beta == null; it++) {
            double[] b = weighted(x, y, bound, delta, null);
            double[] r = residuals(x, y, b);
            double alpha = 1.0;
            int block = -1;
            for (int j = 0; j < n; j++) {
                double p = r[j] - theta[j];
                if (bound[j] != 0.0 || p == 0.0) {
                    continue;
                }
                double limit = ((p > 0.0 ? delta : -delta) - theta[j]) / p;
                if (limit < alpha) {
                    alpha = limit;
                    block = j;
                }
            }
            if (block >= 0) {
                for (int j = 0; j < n; j++) {
                    if (bound[j] == 0.0) {
                        theta[j] += alpha * (r[j] - theta[j]);
                    }
                }
                bound[block] = r[block] - theta[block] > 0.0 ? 1.0 : -1.0;
                theta[block] = bound[block] * delta;
                continue;
            }
            for (int j = 0; j < n; j++) {
                theta[j] = bound[j] == 0.0 ? r[j] : bound[j] * delta;
            }
            double worst = 0.0;
            int leave = -1;
            for (int j = 0; j < n; j++) {
                double m2 = bound[j] * r[j] - delta;
                if (bound[j] != 0.0 && m2 < worst) {
                    worst = m2;
                    leave = j;
                }
            }
            if (leave >= 0) {
                bound[leave] = 0.0;
            } else {
                beta = b;
            }
        }
        if (beta == null) {
            throw new QfError("E_NO_CONVERGENCE", "the Huber fit did not settle");
        }
        double obj = objective(x, y, beta, delta);
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
        return solve3(a, rhs);
    }

    /**
     * Gaussian elimination with partial pivoting and an exact-zero pivot test, as Python's
     * {@code lu_solve}. Ruling D38b has already rejected bases singular to working precision, so the
     * shared solver's relative pivot test must not reject the systems it lets through.
     */
    private static double[] solve3(double[][] input, double[] rhs) {
        double[][] m = {input[0].clone(), input[1].clone(), input[2].clone()};
        double[] x = rhs.clone();
        for (int k = 0; k < 3; k++) {
            int p = k;
            for (int i = k + 1; i < 3; i++) {
                if (Math.abs(m[i][k]) > Math.abs(m[p][k])) {
                    p = i;
                }
            }
            if (m[p][k] == 0.0) {
                throw new QfError("E_SINGULAR", "the matrix is singular to working precision");
            }
            if (p != k) {
                double[] t = m[k];
                m[k] = m[p];
                m[p] = t;
                double tx = x[k];
                x[k] = x[p];
                x[p] = tx;
            }
            for (int i = k + 1; i < 3; i++) {
                double factor = m[i][k] / m[k][k];
                if (factor != 0.0) {
                    for (int j = k; j < 3; j++) {
                        m[i][j] -= factor * m[k][j];
                    }
                    x[i] -= factor * x[k];
                }
            }
        }
        for (int i = 2; i >= 0; i--) {
            double total = x[i];
            for (int j = i + 1; j < 3; j++) {
                total -= m[i][j] * x[j];
            }
            x[i] = total / m[i][i];
        }
        return x;
    }
}
