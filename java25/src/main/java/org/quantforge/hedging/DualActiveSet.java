package org.quantforge.hedging;

import org.quantforge.core.QfError;

/**
 * Strictly convex quadratic programme {@code min 1/2 y'Gy + a'y} subject to {@code C y >= d}, by the dual active-set
 * method of Goldfarb and Idnani (Math. Programming 27, 1983). It starts from the unconstrained minimiser and adds the
 * most violated constraint until none is violated, so it needs no feasible start, and it proves infeasibility when a
 * violated constraint can be reached neither by a primal step nor by dropping an active one.
 */
final class DualActiveSet {
    private DualActiveSet() {}

    /** A step direction whose part outside the active span is this small, relative to the whole, is zero. */
    private static final double ZERO_STEP = 1e-10;
    /** Relative slack before a constraint counts as violated. */
    private static final double VIOLATION = 1e-12;

    /**
     * The minimiser; for each constraint, whether it is in the final active set and its multiplier (0 when inactive),
     * with {@code G y + a = sum_i multiplier_i C_i}.
     */
    record Result(double[] y, boolean[] active, double[] multipliers) {}

    /**
     * Solves the programme. {@code g} must be symmetric positive definite.
     *
     * @throws QfError {@code E_INFEASIBLE} when no {@code y} satisfies the constraints
     */
    static Result solve(double[][] g, double[] a, double[][] c, double[] d) {
        int n = g.length;
        int p = c.length;
        double[][] l = Dense.cholesky(g);
        double[][] j = new double[n][n]; // J = L^{-T}, so J J' = G^{-1}
        for (int col = 0; col < n; col++) {
            for (int i = n - 1; i >= 0; i--) {
                double s = i == col ? 1.0 : 0.0;
                for (int k = i + 1; k < n; k++) {
                    s -= l[k][i] * j[k][col];
                }
                j[i][col] = s / l[i][i];
            }
        }
        double[] jta = mulT(j, a);
        double[] y = new double[n];
        for (int i = 0; i < n; i++) {
            y[i] = -Dense.dot(j[i], jta);
        }
        double[][] r = new double[n][n];
        int[] act = new int[n];
        double[] u = new double[n];
        boolean[] isActive = new boolean[p];
        int q = 0;
        for (int iter = 0; iter < LeastSquaresHedge.iterationCap(n + p); iter++) { // R6-6.1: 10 (n + p) + 100
            int pick = mostViolated(c, d, y, isActive);
            if (pick < 0) {
                double[] lambda = new double[p];
                for (int k = 0; k < q; k++) {
                    lambda[act[k]] = u[k];
                }
                return new Result(y, isActive, lambda);
            }
            double[] np = c[pick];
            double uplus = 0.0;
            while (true) {
                double[] dv = mulT(j, np);
                double[] z = new double[n];
                double d2 = 0.0;
                double dAll = 0.0;
                for (int k = 0; k < n; k++) {
                    dAll += dv[k] * dv[k];
                    if (k >= q) {
                        d2 += dv[k] * dv[k];
                        for (int i = 0; i < n; i++) {
                            z[i] += j[i][k] * dv[k];
                        }
                    }
                }
                double[] rr = backSolve(r, dv, q);
                double t1 = Double.POSITIVE_INFINITY;
                int drop = -1;
                for (int k = 0; k < q; k++) {
                    if (rr[k] > 0.0 && u[k] / rr[k] < t1) {
                        t1 = u[k] / rr[k];
                        drop = k;
                    }
                }
                boolean noPrimal = Math.sqrt(d2) <= ZERO_STEP * Math.sqrt(dAll);
                double t2 = noPrimal ? Double.POSITIVE_INFINITY : -(Dense.dot(np, y) - d[pick]) / Dense.dot(z, np);
                if (noPrimal && drop < 0) {
                    throw new QfError("E_INFEASIBLE", "no point satisfies the bounds and equalities");
                }
                double t = Math.min(t1, t2);
                if (!noPrimal) {
                    for (int i = 0; i < n; i++) {
                        y[i] += t * z[i];
                    }
                }
                for (int k = 0; k < q; k++) {
                    u[k] -= t * rr[k];
                }
                uplus += t;
                if (!noPrimal && t2 <= t1) {
                    addColumn(j, r, dv, q);
                    act[q] = pick;
                    u[q] = uplus;
                    isActive[pick] = true;
                    q++;
                    break;
                }
                isActive[act[drop]] = false;
                dropColumn(j, r, act, u, drop, q);
                q--;
            }
        }
        throw new QfError("E_NO_CONVERGENCE", "active-set iterations exhausted");
    }

    private static int mostViolated(double[][] c, double[] d, double[] y, boolean[] isActive) {
        int pick = -1;
        double worst = 0.0;
        for (int i = 0; i < c.length; i++) {
            if (isActive[i]) {
                continue;
            }
            double s = Dense.dot(c[i], y) - d[i];
            double scale = Math.abs(d[i]);
            double norm = 0.0;
            for (int k = 0; k < y.length; k++) {
                scale += Math.abs(c[i][k] * y[k]);
                norm += c[i][k] * c[i][k];
            }
            if (s < -VIOLATION * scale) {
                double v = s / Math.sqrt(norm);
                if (v < worst) {
                    worst = v;
                    pick = i;
                }
            }
        }
        return pick;
    }

    private static double[] mulT(double[][] j, double[] x) {
        return Dense.mulT(j, x, j.length);
    }

    private static double[] backSolve(double[][] r, double[] dv, int q) {
        double[] x = new double[q];
        for (int i = q - 1; i >= 0; i--) {
            double s = dv[i];
            for (int k = i + 1; k < q; k++) {
                s -= r[i][k] * x[k];
            }
            x[i] = s / r[i][i];
        }
        return x;
    }

    /** Rotates {@code dv[q..]} onto {@code dv[q]}, applying the same rotations to J, then appends it to R. */
    private static void addColumn(double[][] j, double[][] r, double[] dv, int q) {
        int n = j.length;
        for (int k = n - 1; k > q; k--) {
            if (dv[k] == 0.0) {
                continue;
            }
            double h = Math.hypot(dv[k - 1], dv[k]);
            double cs = dv[k - 1] / h;
            double sn = dv[k] / h;
            dv[k - 1] = h;
            dv[k] = 0.0;
            rotateColumns(j, k - 1, k, cs, sn);
        }
        for (int i = 0; i <= q; i++) {
            r[i][q] = dv[i];
        }
    }

    /** Removes active constraint {@code drop}, restoring R to upper-triangular form by Givens rotations. */
    private static void dropColumn(double[][] j, double[][] r, int[] act, double[] u, int drop, int q) {
        for (int k = drop; k < q - 1; k++) {
            act[k] = act[k + 1];
            u[k] = u[k + 1];
            for (int i = 0; i < q; i++) {
                r[i][k] = r[i][k + 1];
            }
        }
        for (int i = 0; i < q; i++) {
            r[i][q - 1] = 0.0;
        }
        for (int k = drop; k < q - 1; k++) {
            double a = r[k][k];
            double b = r[k + 1][k];
            if (b == 0.0) {
                continue;
            }
            double h = Math.hypot(a, b);
            double cs = a / h;
            double sn = b / h;
            for (int col = k; col < q - 1; col++) {
                double x = r[k][col];
                double y = r[k + 1][col];
                r[k][col] = cs * x + sn * y;
                r[k + 1][col] = -sn * x + cs * y;
            }
            rotateColumns(j, k, k + 1, cs, sn);
        }
    }

    private static void rotateColumns(double[][] j, int a, int b, double cs, double sn) {
        for (double[] row : j) {
            double x = row[a];
            double y = row[b];
            row[a] = cs * x + sn * y;
            row[b] = -sn * x + cs * y;
        }
    }
}
