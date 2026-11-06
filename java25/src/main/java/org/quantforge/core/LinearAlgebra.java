package org.quantforge.core;

import java.util.Arrays;

/** Dense solves, Cholesky, symmetric eigenvalues and a pivoted tridiagonal solve. */
public final class LinearAlgebra {
    private LinearAlgebra() {}

    private static double maxAbs(double[][] a) {
        double m = 0.0;
        for (double[] row : a) {
            for (double v : row) {
                m = Math.max(m, Math.abs(v));
            }
        }
        return m;
    }

    private static void checkSquare(double[][] a) {
        if (a.length == 0) {
            throw new QfError("E_INPUT", "empty matrix", "a");
        }
        for (double[] row : a) {
            if (row.length != a.length) {
                throw new QfError("E_INPUT", "matrix is ragged or not square", "a");
            }
        }
    }

    private static void checkSymmetric(double[][] a) {
        checkSquare(a);
        double limit = 1e-12 * maxAbs(a);
        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < i; j++) {
                if (Math.abs(a[i][j] - a[j][i]) > limit) {
                    throw new QfError("E_INPUT", "matrix is not symmetric", "a");
                }
            }
        }
    }

    private static double[][] copy(double[][] input) {
        double[][] a = new double[input.length][];
        for (int i = 0; i < a.length; i++) {
            a[i] = input[i].clone();
        }
        return a;
    }

    public static double[] solve(double[][] input, double[] rhs) {
        checkSquare(input);
        int n = input.length;
        if (rhs.length != n) {
            throw new QfError("E_INPUT", "wrong vector length", "b");
        }
        double[][] a = copy(input);
        double[] x = rhs.clone();
        double limit = 1e-14 * maxAbs(a);
        for (int k = 0; k < n; k++) {
            int p = k;
            for (int i = k + 1; i < n; i++) {
                if (Math.abs(a[i][k]) > Math.abs(a[p][k])) {
                    p = i;
                }
            }
            double pivot = Math.abs(a[p][k]);
            if (pivot <= limit) {
                throw new QfError("E_SINGULAR", "pivot below limit");
            }
            double[] t = a[k];
            a[k] = a[p];
            a[p] = t;
            double tx = x[k];
            x[k] = x[p];
            x[p] = tx;
            for (int i = k + 1; i < n; i++) {
                double f = a[i][k] / a[k][k];
                for (int j = k; j < n; j++) {
                    a[i][j] -= f * a[k][j];
                }
                x[i] -= f * x[k];
            }
        }
        for (int i = n - 1; i >= 0; i--) {
            double s = x[i];
            for (int j = i + 1; j < n; j++) {
                s -= a[i][j] * x[j];
            }
            x[i] = s / a[i][i];
        }
        return x;
    }

    public static double[][] cholesky(double[][] a) {
        checkSymmetric(a);
        int n = a.length;
        double[][] l = new double[n][n];
        for (int j = 0; j < n; j++) {
            double d = a[j][j];
            for (int k = 0; k < j; k++) {
                d -= l[j][k] * l[j][k];
            }
            if (d <= 0.0) {
                throw new QfError("E_NOT_POSITIVE_DEFINITE", "pivot is not positive");
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

    /** Eigenvalues, ascending, by cyclic Jacobi rotations. */
    public static double[] eigenSymmetric(double[][] input) {
        checkSymmetric(input);
        int n = input.length;
        double[][] a = copy(input);
        for (int sweep = 0; sweep < 100; sweep++) {
            double off = 0.0;
            double diag = 0.0;
            for (int i = 0; i < n; i++) {
                diag += a[i][i] * a[i][i];
                for (int j = 0; j < i; j++) {
                    off += a[i][j] * a[i][j];
                }
            }
            if (off <= 1e-36 * diag || off == 0.0) {
                double[] v = new double[n];
                for (int i = 0; i < n; i++) {
                    v[i] = a[i][i];
                }
                Arrays.sort(v);
                return v;
            }
            for (int p = 0; p < n - 1; p++) {
                for (int q = p + 1; q < n; q++) {
                    if (a[p][q] != 0.0) {
                        rotate(a, p, q);
                    }
                }
            }
        }
        throw new QfError("E_NO_CONVERGENCE", "Jacobi sweeps exhausted");
    }

    private static void rotate(double[][] a, int p, int q) {
        double theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
        double t = Math.copySign(1.0, theta) / (Math.abs(theta) + Math.sqrt(theta * theta + 1.0));
        double c = 1.0 / Math.sqrt(t * t + 1.0);
        double s = t * c;
        for (int k = 0; k < a.length; k++) {
            double akp = a[k][p];
            double akq = a[k][q];
            a[k][p] = c * akp - s * akq;
            a[k][q] = s * akp + c * akq;
        }
        for (int k = 0; k < a.length; k++) {
            double apk = a[p][k];
            double aqk = a[q][k];
            a[p][k] = c * apk - s * aqk;
            a[q][k] = s * apk + c * aqk;
        }
        a[p][q] = 0.0; // Zero by construction; leaving the rounding residue would stall the stopping test.
        a[q][p] = 0.0;
    }

    /** Tridiagonal solve with partial pivoting. Overwrites its arguments and returns {@code b}. */
    static double[] solveTridiagonal(double[] dl, double[] d, double[] du, double[] b) {
        int n = d.length;
        double[] du2 = new double[n];
        for (int i = 0; i < n - 1; i++) {
            if (Math.abs(d[i]) >= Math.abs(dl[i])) {
                if (d[i] == 0.0) {
                    throw new QfError("E_SINGULAR", "singular tridiagonal system");
                }
                double f = dl[i] / d[i];
                d[i + 1] -= f * du[i];
                b[i + 1] -= f * b[i];
            } else {
                double f = d[i] / dl[i];
                d[i] = dl[i];
                double t = d[i + 1];
                d[i + 1] = du[i] - f * t;
                du[i] = t;
                if (i < n - 2) {
                    du2[i] = du[i + 1];
                    du[i + 1] = -f * du[i + 1];
                }
                double tb = b[i];
                b[i] = b[i + 1];
                b[i + 1] = tb - f * b[i + 1];
            }
        }
        if (d[n - 1] == 0.0) {
            throw new QfError("E_SINGULAR", "singular tridiagonal system");
        }
        b[n - 1] /= d[n - 1];
        if (n > 1) {
            b[n - 2] = (b[n - 2] - du[n - 2] * b[n - 1]) / d[n - 2];
        }
        for (int i = n - 3; i >= 0; i--) {
            b[i] = (b[i] - du[i] * b[i + 1] - du2[i] * b[i + 2]) / d[i];
        }
        return b;
    }
}
