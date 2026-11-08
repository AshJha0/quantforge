package org.quantforge.risk;

import org.quantforge.core.QfError;

/** Correlation validation, nearest correlation (Higham with Dykstra), implied correlation and dispersion
 * (correlation.md, rulings E-B18 to E-B21). */
public final class Correlation {
    private Correlation() {}

    public static void checkSquare(double[][] m) {
        if (m.length == 0) {
            throw new QfError("E_INPUT", "matrix is empty", "matrix");
        }
        for (double[] r : m) {
            if (r.length != m.length) {
                throw new QfError("E_INPUT", "matrix is not square", "matrix");
            }
        }
    }

    public static boolean symmetric(double[][] m) {
        for (int i = 0; i < m.length; i++) {
            for (int j = 0; j < i; j++) {
                if (m[i][j] != m[j][i]) {
                    return false;
                }
            }
        }
        return true;
    }

    public record Validation(boolean symmetric, boolean unitDiagonal, boolean inRange, double minEigenvalue) {
        public boolean psd() {
            return minEigenvalue >= -1e-10;
        }

        public boolean valid() {
            return symmetric && unitDiagonal && inRange && psd();
        }
    }

    public static Validation validate(double[][] m) {
        checkSquare(m);
        int n = m.length;
        boolean unit = true;
        boolean range = true;
        double[][] s = new double[n][n];
        for (int i = 0; i < n; i++) {
            unit &= m[i][i] == 1.0;
            for (int j = 0; j < n; j++) {
                range &= m[i][j] >= -1.0 && m[i][j] <= 1.0;
                s[i][j] = (m[i][j] + m[j][i]) / 2.0;
            }
        }
        double min = Double.POSITIVE_INFINITY;
        for (double w : eigen(s).values()) {
            min = Math.min(min, w);
        }
        return new Validation(symmetric(m), unit, range, min);
    }

    public record Eigen(double[] values, double[][] vectors) {}

    /** Eigenvalues and eigenvectors (columns) of a symmetric matrix, cyclic Jacobi. */
    static Eigen eigen(double[][] input) {
        int n = input.length;
        double[][] a = new double[n][];
        double[][] v = new double[n][n];
        for (int i = 0; i < n; i++) {
            a[i] = input[i].clone();
            v[i][i] = 1.0;
        }
        for (int sweep = 0; sweep < 100; sweep++) {
            double off = 0.0;
            double diag = 0.0;
            for (int i = 0; i < n; i++) {
                diag += a[i][i] * a[i][i];
                for (int j = 0; j < i; j++) {
                    off += a[i][j] * a[i][j];
                }
            }
            if (off == 0.0 || off <= 1e-36 * diag) {
                break;
            }
            for (int p = 0; p < n - 1; p++) {
                for (int q = p + 1; q < n; q++) {
                    if (a[p][q] == 0.0) {
                        continue;
                    }
                    double theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
                    double t = Math.copySign(1.0, theta) / (Math.abs(theta) + Math.sqrt(theta * theta + 1.0));
                    double c = 1.0 / Math.sqrt(t * t + 1.0);
                    double s = t * c;
                    for (int k = 0; k < n; k++) {
                        double akp = a[k][p];
                        double akq = a[k][q];
                        a[k][p] = c * akp - s * akq;
                        a[k][q] = s * akp + c * akq;
                    }
                    for (int k = 0; k < n; k++) {
                        double apk = a[p][k];
                        double aqk = a[q][k];
                        a[p][k] = c * apk - s * aqk;
                        a[q][k] = s * apk + c * aqk;
                    }
                    for (int k = 0; k < n; k++) {
                        double vkp = v[k][p];
                        double vkq = v[k][q];
                        v[k][p] = c * vkp - s * vkq;
                        v[k][q] = s * vkp + c * vkq;
                    }
                }
            }
        }
        double[] w = new double[n];
        for (int i = 0; i < n; i++) {
            w[i] = a[i][i];
        }
        return new Eigen(w, v);
    }

    /** V max(w, 0) V^T, symmetrised. */
    static double[][] projectPsd(double[][] r) {
        int n = r.length;
        Eigen e = eigen(r);
        double[][] x = new double[n][n];
        for (int k = 0; k < n; k++) {
            double w = Math.max(e.values()[k], 0.0);
            if (w == 0.0) {
                continue;
            }
            for (int i = 0; i < n; i++) {
                double vi = e.vectors()[i][k] * w;
                for (int j = 0; j < n; j++) {
                    x[i][j] += vi * e.vectors()[j][k];
                }
            }
        }
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < i; j++) {
                double m = (x[i][j] + x[j][i]) / 2.0;
                x[i][j] = m;
                x[j][i] = m;
            }
        }
        return x;
    }

    public record Nearest(double[][] matrix, double distance) {}

    /** Higham's alternating projections with Dykstra's correction, until the iterate stops changing. */
    public static Nearest nearest(double[][] m) {
        checkSquare(m);
        if (!symmetric(m)) {
            throw new QfError("E_INPUT", "matrix must be symmetric", "matrix");
        }
        int n = m.length;
        double[][] y = copy(m);
        double[][] xPrev = copy(m);
        double[][] ds = new double[n][n];
        boolean done = false;
        for (int it = 0; it < 100_000 && !done; it++) {
            double[][] r = new double[n][n];
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    r[i][j] = y[i][j] - ds[i][j];
                }
            }
            double[][] x = projectPsd(r);
            double dx = 0.0;
            double dy = 0.0;
            double gap = 0.0;
            double nx = 0.0;
            double ny = 0.0;
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    ds[i][j] = x[i][j] - r[i][j];
                    double next = i == j ? 1.0 : x[i][j];
                    dx += sq(x[i][j] - xPrev[i][j]);
                    dy += sq(next - y[i][j]);
                    gap += sq(next - x[i][j]);
                    nx += sq(x[i][j]);
                    ny += sq(next);
                    y[i][j] = next;
                }
            }
            xPrev = x;
            // Higham's test: relative changes in X and Y, and the X-Y gap, all below TOL (ruling E-B31)
            done = it > 0 && Math.sqrt(Math.max(dx / nx, Math.max(dy, gap) / ny)) < TOL;
        }
        if (!done) {
            throw new QfError("E_NO_CONVERGENCE", "nearest correlation did not converge");
        }
        double d = 0.0;
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                d += (y[i][j] - m[i][j]) * (y[i][j] - m[i][j]);
            }
        }
        return new Nearest(y, Math.sqrt(d));
    }

    /** Higham's stopping tolerance, at most 1e-12 (ruling E-B31). */
    static final double TOL = 1e-13;

    private static double sq(double x) {
        return x * x;
    }

    private static double[][] copy(double[][] m) {
        double[][] c = new double[m.length][];
        for (int i = 0; i < m.length; i++) {
            c[i] = m[i].clone();
        }
        return c;
    }

    /** (sigma_I^2 - sum w^2 sigma^2) / sum_{i != j} w_i w_j sigma_i sigma_j; not clipped (E-B20). */
    public static double implied(double[] w, double[] s, double index) {
        double own = 0.0;
        double ws = 0.0;
        for (int i = 0; i < w.length; i++) {
            own += w[i] * w[i] * s[i] * s[i];
            ws += w[i] * s[i];
        }
        return (index * index - own) / (ws * ws - own);
    }

    /** Weights >= 0 with at least two positive (ruling E-B33); a zero weight drops its name. */
    public static void checkWeights(double[] w) {
        checkNonNegative(w);
        checkTwoPositive(w);
    }

    public static void checkNonNegative(double[] w) {
        for (double x : w) {
            if (!(x >= 0.0)) {
                throw new QfError("E_DOMAIN", "weights must not be negative", "weights");
            }
        }
    }

    public static void checkTwoPositive(double[] w) {
        int positive = 0;
        for (double x : w) {
            if (x > 0.0) {
                positive++;
            }
        }
        if (positive < 2) {
            throw new QfError("E_DOMAIN", "need at least two positive weights", "weights");
        }
    }

    public static void checkNames(int... lengths) {
        for (int l : lengths) {
            if (l != lengths[0] || l < 2) {
                throw new QfError("E_INPUT", "need at least two names and lists of one length");
            }
        }
    }

    public static void checkPositive(String key, double... x) {
        for (double v : x) {
            if (!(v > 0.0)) {
                throw new QfError("E_DOMAIN", key + " must be above 0", key);
            }
        }
    }
}
