package org.quantforge.hedging;

import org.quantforge.core.Finite;

import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;

/**
 * min |A x + b|_W^2 + lambda sum c_i |x_i| (stage-b-hedges.md). Coordinate descent finds the active set, and an
 * exact solve on that set gives the answer, accepted only if it meets the first-order conditions.
 */
public final class HedgeSolver {
    private HedgeSolver() {}

    public record Solution(double[] x, double[] residual, double objective) {}

    private static final int MAX_SWEEPS = 200_000;

    public static Solution solve(double[][] a, double[] b, double[] weights, double[] costs, double lambda) {
        Finite.check("a", a);
        Finite.check("b", b);
        Finite.check("weights", weights);
        Finite.check("costs", costs);
        Finite.check("lambda", lambda);
        int rows = a.length;
        if (rows == 0 || b.length != rows || weights.length != rows) {
            throw new QfError("E_INPUT", "length mismatch");
        }
        int n = a[0].length;
        for (double[] row : a) {
            if (row.length != n) {
                throw new QfError("E_INPUT", "a is ragged", "a");
            }
        }
        if (costs.length != n || n == 0) {
            throw new QfError("E_INPUT", "length mismatch", "costs");
        }
        for (double w : weights) {
            if (!(w > 0.0)) {
                throw new QfError("E_DOMAIN", "weights must be positive", "weights");
            }
        }
        for (double c : costs) {
            if (c < 0.0) {
                throw new QfError("E_DOMAIN", "cost is negative", "costs");
            }
        }
        if (lambda < 0.0) {
            throw new QfError("E_DOMAIN", "lambda is negative", "lambda");
        }
        double[][] q = new double[n][n];
        double[] v = new double[n];
        for (int r = 0; r < rows; r++) {
            for (int i = 0; i < n; i++) {
                v[i] += weights[r] * a[r][i] * b[r];
                for (int j = 0; j < n; j++) {
                    q[i][j] += weights[r] * a[r][i] * a[r][j];
                }
            }
        }
        checkRank(q);
        double[] penalty = new double[n];
        for (int i = 0; i < n; i++) {
            penalty[i] = lambda * costs[i] / 2.0;
        }
        boolean[] settled = new boolean[1];
        double[] x = descend(q, v, penalty, settled);
        double[] exact = polish(q, v, penalty, x);
        if (exact != null) {
            x = exact;
        } else if (!settled[0]) {
            throw new QfError("E_NO_CONVERGENCE", "coordinate descent did not settle");
        }
        double[] residual = new double[rows];
        double objective = 0.0;
        for (int r = 0; r < rows; r++) {
            double s = b[r];
            for (int i = 0; i < n; i++) {
                s += a[r][i] * x[i];
            }
            residual[r] = s;
            objective += weights[r] * s * s;
        }
        for (int i = 0; i < n; i++) {
            objective += lambda * costs[i] * Math.abs(x[i]);
        }
        return new Solution(x, residual, objective);
    }

    /** A pivot of A^T W A at or below 1e-12 of its largest entry means no full column rank. */
    private static void checkRank(double[][] q) {
        int n = q.length;
        double largest = 0.0;
        double[][] m = new double[n][];
        for (int i = 0; i < n; i++) {
            m[i] = q[i].clone();
            for (double e : q[i]) {
                largest = Math.max(largest, Math.abs(e));
            }
        }
        for (int k = 0; k < n; k++) {
            if (m[k][k] <= 1e-12 * largest) {
                throw new QfError("E_SINGULAR", "A has no full column rank");
            }
            for (int i = k + 1; i < n; i++) {
                double f = m[i][k] / m[k][k];
                for (int j = k; j < n; j++) {
                    m[i][j] -= f * m[k][j];
                }
            }
        }
    }

    private static double[] descend(double[][] q, double[] v, double[] penalty, boolean[] settled) {
        int n = v.length;
        double[] x = new double[n];
        for (int sweep = 0; sweep < MAX_SWEEPS; sweep++) {
            double change = 0.0;
            for (int i = 0; i < n; i++) {
                double s = -v[i];
                for (int j = 0; j < n; j++) {
                    if (j != i) {
                        s -= q[i][j] * x[j];
                    }
                }
                double next = Math.signum(s) * Math.max(Math.abs(s) - penalty[i], 0.0) / q[i][i];
                change = Math.max(change, Math.abs(next - x[i]));
                x[i] = next;
            }
            if (change <= 1e-13 * (1.0 + maxAbs(x))) {
                settled[0] = true;
                break;
            }
        }
        return x;
    }

    private static double maxAbs(double[] x) {
        double m = 0.0;
        for (double e : x) {
            m = Math.max(m, Math.abs(e));
        }
        return m;
    }

    /** Solves exactly on the non-zero set with its signs; null if that fails the first-order conditions. */
    private static double[] polish(double[][] q, double[] v, double[] penalty, double[] x) {
        int n = x.length;
        int[] index = new int[n];
        int count = 0;
        for (int i = 0; i < n; i++) {
            if (x[i] != 0.0) {
                index[count++] = i;
            }
        }
        double[] out = new double[n];
        if (count > 0) {
            double[][] m = new double[count][count];
            double[] rhs = new double[count];
            for (int r = 0; r < count; r++) {
                for (int c = 0; c < count; c++) {
                    m[r][c] = q[index[r]][index[c]];
                }
                rhs[r] = -v[index[r]] - penalty[index[r]] * Math.signum(x[index[r]]);
            }
            double[] s = LinearAlgebra.solve(m, rhs);
            for (int r = 0; r < count; r++) {
                if (Math.signum(s[r]) != Math.signum(x[index[r]])) {
                    return null;
                }
                out[index[r]] = s[r];
            }
        }
        for (int i = 0; i < n; i++) {
            if (out[i] == 0.0) {
                double g = v[i];
                for (int j = 0; j < n; j++) {
                    g += q[i][j] * out[j];
                }
                if (Math.abs(g) > penalty[i] * (1.0 + 1e-12) + 1e-12) {
                    return null;
                }
            }
        }
        return out;
    }
}
