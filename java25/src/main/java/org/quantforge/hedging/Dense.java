package org.quantforge.hedging;

import org.quantforge.core.QfError;

/**
 * Dense helpers for the stage I hedge solvers: products, a symmetric eigen-decomposition with vectors, a Householder
 * QR and a Cholesky factor. Package-private; every caller has already checked shapes and finiteness.
 */
final class Dense {
    private Dense() {}

    /** Ruling I-3: the one relative threshold for every rank or singularity decision. */
    static final double RANK_TOL = 1e-12;

    /** A symmetric eigen-decomposition: {@code values[j]} belongs to column {@code j} of {@code vectors}. */
    record Eigen(double[] values, double[][] vectors) {
        /** The largest eigenvalue in absolute value, 0 for an empty matrix. */
        double maxAbs() {
            double m = 0.0;
            for (double v : values) {
                m = Math.max(m, Math.abs(v));
            }
            return m;
        }
    }

    static double dot(double[] x, double[] y) {
        double s = 0.0;
        for (int i = 0; i < x.length; i++) {
            s += x[i] * y[i];
        }
        return s;
    }

    static double[] mul(double[][] a, double[] x) {
        double[] y = new double[a.length];
        for (int i = 0; i < a.length; i++) {
            y[i] = dot(a[i], x);
        }
        return y;
    }

    /** {@code a^T x} for an {@code m x n} matrix {@code a}. */
    static double[] mulT(double[][] a, double[] x, int n) {
        double[] y = new double[n];
        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < n; j++) {
                y[j] += a[i][j] * x[i];
            }
        }
        return y;
    }

    /** {@code A^T diag(w) A + ridge I}, symmetric by construction. */
    static double[][] gram(double[][] a, double[] w, double ridge, int n) {
        double[][] h = new double[n][n];
        for (int i = 0; i < a.length; i++) {
            for (int p = 0; p < n; p++) {
                double wp = w[i] * a[i][p];
                if (wp == 0.0) {
                    continue;
                }
                for (int q = p; q < n; q++) {
                    h[p][q] += wp * a[i][q];
                }
            }
        }
        for (int p = 0; p < n; p++) {
            h[p][p] += ridge;
            for (int q = 0; q < p; q++) {
                h[p][q] = h[q][p];
            }
        }
        return h;
    }

    /** {@code Z^T H Z} for {@code H} n x n and {@code Z} n x r, symmetrised. */
    static double[][] congruence(double[][] h, double[][] z, int r) {
        int n = h.length;
        double[][] hz = new double[n][r];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < r; j++) {
                double s = 0.0;
                for (int k = 0; k < n; k++) {
                    s += h[i][k] * z[k][j];
                }
                hz[i][j] = s;
            }
        }
        double[][] g = new double[r][r];
        for (int p = 0; p < r; p++) {
            for (int q = p; q < r; q++) {
                double s = 0.0;
                for (int k = 0; k < n; k++) {
                    s += z[k][p] * hz[k][q];
                }
                g[p][q] = s;
                g[q][p] = s;
            }
        }
        return g;
    }

    /** Eigenvalues and orthonormal eigenvectors of a symmetric matrix by cyclic Jacobi rotations. */
    static Eigen eigen(double[][] input) {
        int n = input.length;
        double[][] a = new double[n][];
        for (int i = 0; i < n; i++) {
            a[i] = input[i].clone();
        }
        double[][] v = new double[n][n];
        for (int i = 0; i < n; i++) {
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
                double[] values = new double[n];
                for (int i = 0; i < n; i++) {
                    values[i] = a[i][i];
                }
                return new Eigen(values, v);
            }
            for (int p = 0; p < n - 1; p++) {
                for (int q = p + 1; q < n; q++) {
                    if (a[p][q] != 0.0) {
                        rotate(a, v, p, q);
                    }
                }
            }
        }
        throw new QfError("E_NO_CONVERGENCE", "Jacobi sweeps exhausted");
    }

    private static void rotate(double[][] a, double[][] v, int p, int q) {
        double theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
        double t = Math.copySign(1.0, theta) / (Math.abs(theta) + Math.sqrt(theta * theta + 1.0));
        double c = 1.0 / Math.sqrt(t * t + 1.0);
        double s = t * c;
        int n = a.length;
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
        a[p][q] = 0.0; // zero by construction; a rounding residue would stall the stopping test
        a[q][p] = 0.0;
        for (int k = 0; k < n; k++) {
            double vkp = v[k][p];
            double vkq = v[k][q];
            v[k][p] = c * vkp - s * vkq;
            v[k][q] = s * vkp + c * vkq;
        }
    }

    /**
     * Householder QR of the n x k matrix {@code m} ({@code k <= n}): returns the full orthogonal {@code Q} (n x n)
     * and writes the upper-triangular k x k factor into {@code r}.
     */
    static double[][] householderQr(double[][] m, int n, int k, double[][] r) {
        double[][] a = new double[n][k];
        for (int i = 0; i < n; i++) {
            System.arraycopy(m[i], 0, a[i], 0, k);
        }
        double[][] vs = new double[k][];
        double[] betas = new double[k];
        for (int j = 0; j < k; j++) {
            double norm = 0.0;
            for (int i = j; i < n; i++) {
                norm = Math.hypot(norm, a[i][j]);
            }
            double[] v = new double[n];
            if (norm == 0.0) {
                vs[j] = v;
                continue;
            }
            double alpha = a[j][j] > 0 ? -norm : norm;
            for (int i = j; i < n; i++) {
                v[i] = a[i][j];
            }
            v[j] -= alpha;
            double vv = 0.0;
            for (int i = j; i < n; i++) {
                vv += v[i] * v[i];
            }
            betas[j] = 2.0 / vv;
            vs[j] = v;
            for (int c = j; c < k; c++) {
                double s = 0.0;
                for (int i = j; i < n; i++) {
                    s += v[i] * a[i][c];
                }
                s *= betas[j];
                for (int i = j; i < n; i++) {
                    a[i][c] -= s * v[i];
                }
            }
        }
        for (int i = 0; i < k; i++) {
            for (int j = 0; j < k; j++) {
                r[i][j] = j >= i ? a[i][j] : 0.0;
            }
        }
        double[][] q = new double[n][n];
        for (int i = 0; i < n; i++) {
            q[i][i] = 1.0;
        }
        for (int j = k - 1; j >= 0; j--) {
            double[] v = vs[j];
            if (betas[j] == 0.0) {
                continue;
            }
            for (int c = 0; c < n; c++) {
                double s = 0.0;
                for (int i = j; i < n; i++) {
                    s += v[i] * q[i][c];
                }
                s *= betas[j];
                for (int i = j; i < n; i++) {
                    q[i][c] -= s * v[i];
                }
            }
        }
        return q;
    }

    /** Lower Cholesky factor of a matrix already known to be positive definite. */
    static double[][] cholesky(double[][] a) {
        int n = a.length;
        double[][] l = new double[n][n];
        for (int j = 0; j < n; j++) {
            double d = a[j][j];
            for (int k = 0; k < j; k++) {
                d -= l[j][k] * l[j][k];
            }
            if (!(d > 0.0)) {
                throw new QfError("E_SINGULAR", "matrix is not positive definite");
            }
            l[j][j] = Math.sqrt(d);
            for (int i = j + 1; i < n; i++) {
                double s = a[i][j];
                for (int k = 0; k < j; k++) {
                    s -= l[i][k] * l[j][k];
                }
                l[i][j] = s / l[j][j];
            }
        }
        return l;
    }

    /** Jacobi factors {@code 1 / sqrt(M_jj)} (ruling R6-6.2); a non-positive diagonal keeps factor 1. */
    static double[] jacobiFactors(double[][] m) {
        double[] d = new double[m.length];
        for (int j = 0; j < m.length; j++) {
            d[j] = m[j][j] > 0.0 ? 1.0 / Math.sqrt(m[j][j]) : 1.0;
        }
        return d;
    }

    /** {@code D M D} with the Jacobi factors of {@code m}. */
    static double[][] jacobiScaled(double[][] m) {
        double[] d = jacobiFactors(m);
        double[][] out = new double[m.length][m.length];
        for (int i = 0; i < m.length; i++) {
            for (int j = 0; j < m.length; j++) {
                out[i][j] = d[i] * m[i][j] * d[j];
            }
        }
        return out;
    }
}
