package org.quantforge.hedging;

import org.quantforge.core.QfError;

/**
 * Stage I hedge solvers on the weighted least-squares residual {@code A x + b} ({@code hedge-solvers.md}): the
 * constrained quadratic programme {@code hedge.qp.solve} and the integer-lot search {@code hedge.integer.solve}.
 *
 * <p>The objective is {@code f(x) = sum_i w_i (A x + b)_i^2 + ridge |x|^2 = x'Hx + 2c'x + b'Wb} with
 * {@code H = A'WA + ridge I} and {@code c = A'Wb}. Equalities are removed by the null-space basis {@code Z} of the
 * equality matrix, and the bounds are handled by a dual active-set method on the reduced problem, which is strictly
 * convex once the singularity checks pass. Every rank decision uses the relative threshold {@code 1e-12} (ruling
 * I-3). Infinite bounds mean no bound.
 */
public final class LeastSquaresHedge {
    private LeastSquaresHedge() {}

    /**
     * A {@code hedge.qp.solve} answer.
     *
     * @param x positions, one per instrument
     * @param residual {@code A x + b}, one per factor
     * @param objective {@code f(x)}
     * @param rank the number of eigenvalues of the reduced Hessian above the threshold
     */
    public record Solution(double[] x, double[] residual, double objective, int rank) {}

    /**
     * A {@code hedge.integer.solve} answer.
     *
     * @param lots whole lots per instrument
     * @param x positions, {@code lot_sizes * lots}
     * @param residual {@code A x + b}
     * @param objective {@code f(x)}
     * @param continuousObjective {@code f} at the bounded continuous solution in lot units
     * @param roundingCost {@code objective - continuousObjective}, never below 0
     */
    public record IntegerSolution(long[] lots, double[] x, double[] residual, double objective,
            double continuousObjective, double roundingCost) {}

    private static QfError input(String key) {
        return new QfError("E_INPUT", key + " has the wrong shape", key);
    }

    private static QfError domain(String key) {
        return new QfError("E_DOMAIN", key + " is out of range", key);
    }

    private static int checkShapes(double[][] a, double[] b, double[] w) {
        if (a.length == 0 || a[0].length == 0) {
            throw input("a");
        }
        int n = a[0].length;
        for (double[] row : a) {
            if (row.length != n) {
                throw input("a");
            }
        }
        if (b.length != a.length) {
            throw input("b");
        }
        if (w.length != a.length) {
            throw input("weights");
        }
        return n;
    }

    private static void checkWeights(double[] w, double ridge) {
        for (double v : w) {
            if (!(v > 0.0)) {
                throw domain("weights");
            }
        }
        if (!(ridge >= 0.0)) {
            throw domain("ridge");
        }
    }

    private static double[] boundsOrFree(double[] bound, int n, double free) {
        double[] out = new double[n];
        java.util.Arrays.fill(out, free);
        if (bound != null) {
            for (int j = 0; j < n; j++) {
                if (!Double.isInfinite(bound[j])) {
                    out[j] = bound[j];
                }
            }
        }
        return out;
    }

    /**
     * Solves {@code hedge.qp.solve}.
     *
     * @param a factor-by-instrument sensitivities, {@code m x n}
     * @param b the book's factor exposures, length {@code m}
     * @param weights factor weights, each {@code > 0}
     * @param ridge Tikhonov weight, {@code >= 0}
     * @param eqMatrix equality rows ({@code k x n}), or null for none
     * @param eqRhs equality right-hand side, or null for none
     * @param lower lower bounds (infinite for none), or null
     * @param upper upper bounds (infinite for none), or null
     * @param minNorm true for {@code singular = MIN_NORM}
     * @return the unique minimiser, or the minimum-norm one under {@code MIN_NORM}
     * @throws QfError {@code E_INPUT}, {@code E_DOMAIN}, {@code E_SINGULAR} or {@code E_INFEASIBLE}, in the
     *     specification's order
     */
    public static Solution solve(double[][] a, double[] b, double[] weights, double ridge, double[][] eqMatrix,
            double[] eqRhs, double[] lower, double[] upper, boolean minNorm) {
        int n = checkShapes(a, b, weights);
        if ((eqMatrix == null) != (eqRhs == null)) {
            throw input(eqMatrix == null ? "eq_matrix" : "eq_rhs");
        }
        int k = eqMatrix == null ? 0 : eqMatrix.length;
        if (eqMatrix != null) {
            for (double[] row : eqMatrix) {
                if (row.length != n) {
                    throw input("eq_matrix");
                }
            }
            if (eqRhs.length != k) {
                throw input("eq_rhs");
            }
        }
        if (lower != null && lower.length != n) {
            throw input("lower");
        }
        if (upper != null && upper.length != n) {
            throw input("upper");
        }
        double[] lo = boundsOrFree(lower, n, Double.NEGATIVE_INFINITY);
        double[] hi = boundsOrFree(upper, n, Double.POSITIVE_INFINITY);
        boolean bounded = false;
        for (int j = 0; j < n; j++) {
            bounded |= lo[j] > Double.NEGATIVE_INFINITY || hi[j] < Double.POSITIVE_INFINITY;
        }
        if (minNorm && bounded) {
            throw new QfError("E_INPUT", "MIN_NORM does not take bounds", "singular");
        }
        checkWeights(weights, ridge);
        for (int j = 0; j < n; j++) {
            if (lo[j] > hi[j]) {
                throw domain("lower");
            }
        }
        // Check 4: equality rank.
        double[][] q = null;
        double[] xp = new double[n];
        if (k > n) {
            throw new QfError("E_SINGULAR", "more equalities than instruments", "eq_matrix");
        }
        if (k > 0) {
            double[][] et = new double[n][k];
            for (int i = 0; i < k; i++) {
                for (int j = 0; j < n; j++) {
                    et[j][i] = eqMatrix[i][j];
                }
            }
            double[] sv = org.quantforge.core.LinearAlgebra.singularValues(et);
            if (!(sv[k - 1] > Dense.RANK_TOL * sv[0])) {
                throw new QfError("E_SINGULAR", "equality rows are dependent", "eq_matrix");
            }
            double[][] rf = new double[k][k];
            q = Dense.householderQr(et, n, k, rf);
            double[] v = new double[k]; // R' v = e, then x_p = Q1 v is the least-norm solution of E x = e
            for (int i = 0; i < k; i++) {
                double s = eqRhs[i];
                for (int t = 0; t < i; t++) {
                    s -= rf[t][i] * v[t];
                }
                v[i] = s / rf[i][i];
            }
            for (int j = 0; j < n; j++) {
                for (int i = 0; i < k; i++) {
                    xp[j] += q[j][i] * v[i];
                }
            }
        }
        // Check 5: reduced Hessian.
        double[][] h = Dense.gram(a, weights, ridge, n);
        double[] wb = new double[b.length];
        for (int i = 0; i < b.length; i++) {
            wb[i] = weights[i] * b[i];
        }
        double[] c = Dense.mulT(a, wb, n);
        double threshold = Dense.RANK_TOL * Dense.eigen(h).maxAbs();
        int r = n - k;
        double[][] z = new double[n][r];
        for (int j = 0; j < n; j++) {
            for (int t = 0; t < r; t++) {
                z[j][t] = q == null ? (j == t ? 1.0 : 0.0) : q[j][k + t];
            }
        }
        double[][] hr = Dense.congruence(h, z, r);
        Dense.Eigen reduced = Dense.eigen(hr);
        int rank = 0;
        for (double ev : reduced.values()) {
            if (ev > threshold) {
                rank++;
            }
        }
        if (rank < r && !minNorm) {
            throw new QfError("E_SINGULAR", "the reduced Hessian is singular", "a");
        }
        double[] hxp = Dense.mul(h, xp);
        double[] grad = new double[n];
        for (int j = 0; j < n; j++) {
            grad[j] = hxp[j] + c[j];
        }
        double[] gr = Dense.mulT(z, grad, r);
        double[] y;
        boolean[] activeLo = new boolean[n];
        boolean[] activeHi = new boolean[n];
        if (minNorm) {
            y = new double[r];
            double[][] v = reduced.vectors();
            for (int t = 0; t < r; t++) {
                double ev = reduced.values()[t];
                if (ev > threshold) {
                    double coef = 0.0;
                    for (int s = 0; s < r; s++) {
                        coef += v[s][t] * gr[s];
                    }
                    coef /= ev;
                    for (int s = 0; s < r; s++) {
                        y[s] -= coef * v[s][t];
                    }
                }
            }
        } else {
            y = boundedReduced(hr, gr, z, xp, lo, hi, activeLo, activeHi);
        }
        double[] x = new double[n];
        for (int j = 0; j < n; j++) {
            double s = xp[j];
            for (int t = 0; t < r; t++) {
                s += z[j][t] * y[t];
            }
            if (k == 0 && activeLo[j]) {
                s = lo[j];
            } else if (k == 0 && activeHi[j]) {
                s = hi[j];
            }
            x[j] = s + 0.0;
        }
        double[] res = residual(a, b, x);
        return new Solution(x, res, objective(res, weights, ridge, x), rank);
    }

    /** The bounded reduced problem in {@code y}, with {@code x = x_p + Z y}; marks the active bounds. */
    private static double[] boundedReduced(double[][] hr, double[] gr, double[][] z, double[] xp, double[] lo,
            double[] hi, boolean[] activeLo, boolean[] activeHi) {
        int n = xp.length;
        int r = hr.length;
        int count = 0;
        for (int j = 0; j < n; j++) {
            count += (lo[j] > Double.NEGATIVE_INFINITY ? 1 : 0) + (hi[j] < Double.POSITIVE_INFINITY ? 1 : 0);
        }
        if (r == 0) {
            for (int j = 0; j < n; j++) {
                double tol = 1e-10 * Math.max(1.0, Math.abs(xp[j]));
                if (xp[j] < lo[j] - tol || xp[j] > hi[j] + tol) {
                    throw new QfError("E_INFEASIBLE", "the equalities fix a point outside the bounds");
                }
            }
            return new double[0];
        }
        double[][] cons = new double[count][];
        double[] rhs = new double[count];
        int[] which = new int[count];
        int at = 0;
        for (int j = 0; j < n; j++) {
            if (lo[j] > Double.NEGATIVE_INFINITY) {
                cons[at] = z[j].clone();
                rhs[at] = lo[j] - xp[j];
                which[at++] = j + 1;
            }
            if (hi[j] < Double.POSITIVE_INFINITY) {
                cons[at] = new double[r];
                for (int t = 0; t < r; t++) {
                    cons[at][t] = -z[j][t];
                }
                rhs[at] = xp[j] - hi[j];
                which[at++] = -(j + 1);
            }
        }
        DualActiveSet.Result res = DualActiveSet.solve(hr, gr, cons, rhs);
        for (int i = 0; i < count; i++) {
            if (res.active()[i]) {
                if (which[i] > 0) {
                    activeLo[which[i] - 1] = true;
                } else {
                    activeHi[-which[i] - 1] = true;
                }
            }
        }
        return res.y();
    }

    static double[] residual(double[][] a, double[] b, double[] x) {
        double[] r = new double[a.length];
        for (int i = 0; i < a.length; i++) {
            r[i] = Dense.dot(a[i], x) + b[i] + 0.0;
        }
        return r;
    }

    static double objective(double[] res, double[] w, double ridge, double[] x) {
        double f = 0.0;
        for (int i = 0; i < res.length; i++) {
            f += w[i] * res[i] * res[i];
        }
        if (ridge > 0.0) {
            f += ridge * Dense.dot(x, x);
        }
        return f;
    }

    /**
     * Solves {@code hedge.integer.solve}: whole lots {@code n} with {@code x = lot_sizes * n} minimising {@code f},
     * ties broken by ruling I-7 (objective within {@code 1e-12} relative, then the smallest {@code sum |n|}, then
     * the lexicographically smallest {@code n}). The search enumerates the integer points of the ellipsoid
     * {@code f <= f(n_0)} inside the lot box [FP85], where {@code n_0} is the rounded bounded continuous solution.
     *
     * @param a factor-by-instrument sensitivities per unit, {@code m x n}
     * @param b the book's factor exposures, length {@code m}
     * @param weights factor weights, each {@code > 0}
     * @param ridge Tikhonov weight on the positions, {@code >= 0}
     * @param lotSizes units per lot, each {@code > 0}
     * @param lowerLots lower lot bounds (infinite for none), or null
     * @param upperLots upper lot bounds (infinite for none), or null
     * @return the best lots under the tie rule, with the continuous comparison
     * @throws QfError {@code E_INPUT}, {@code E_DOMAIN} or {@code E_SINGULAR}, in the specification's order
     */
    public static IntegerSolution solveLots(double[][] a, double[] b, double[] weights, double ridge,
            double[] lotSizes, double[] lowerLots, double[] upperLots) {
        int n = checkShapes(a, b, weights);
        if (lotSizes.length != n) {
            throw input("lot_sizes");
        }
        if (lowerLots != null && lowerLots.length != n) {
            throw input("lower_lots");
        }
        if (upperLots != null && upperLots.length != n) {
            throw input("upper_lots");
        }
        checkWeights(weights, ridge);
        for (double s : lotSizes) {
            if (!(s > 0.0)) {
                throw domain("lot_sizes");
            }
        }
        double[] lo = boundsOrFree(lowerLots, n, Double.NEGATIVE_INFINITY);
        double[] hi = boundsOrFree(upperLots, n, Double.POSITIVE_INFINITY);
        for (int j = 0; j < n; j++) {
            if (lo[j] > hi[j]) {
                throw domain("lower_lots");
            }
        }
        // The problem in lot units: a column-scaled A, so H_L = L H L and the ridge term ridge |L n|^2.
        double[][] al = new double[a.length][n];
        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < n; j++) {
                al[i][j] = a[i][j] * lotSizes[j];
            }
        }
        double[][] hl = Dense.gram(al, weights, 0.0, n);
        for (int j = 0; j < n; j++) {
            hl[j][j] += ridge * lotSizes[j] * lotSizes[j];
        }
        Dense.Eigen eh = Dense.eigen(hl);
        double minEv = Double.POSITIVE_INFINITY;
        for (double ev : eh.values()) {
            minEv = Math.min(minEv, ev);
        }
        if (!(minEv > Dense.RANK_TOL * eh.maxAbs())) {
            throw new QfError("E_SINGULAR", "the continuous problem in lot units is singular", "a");
        }
        double[] wb = new double[b.length];
        for (int i = 0; i < b.length; i++) {
            wb[i] = weights[i] * b[i];
        }
        double[] cl = Dense.mulT(al, wb, n);
        // Continuous bounded solution in lot units.
        double[][] identity = new double[n][n];
        for (int j = 0; j < n; j++) {
            identity[j][j] = 1.0;
        }
        boolean[] actLo = new boolean[n];
        boolean[] actHi = new boolean[n];
        double[] nc = boundedReduced(hl, cl, identity, new double[n], lo, hi, actLo, actHi);
        for (int j = 0; j < n; j++) {
            nc[j] = actLo[j] ? lo[j] : actHi[j] ? hi[j] : nc[j];
        }
        double contObj = objective(residual(al, b, nc), weights, 0.0, nc) + ridgeTerm(ridge, lotSizes, nc);
        Search s = new Search(al, b, weights, ridge, lotSizes, hl, cl, lo, hi);
        long[] start = new long[n];
        for (int j = 0; j < n; j++) {
            start[j] = (long) Math.max(lo[j], Math.min(hi[j], roundHalfAway(nc[j])));
        }
        s.offer(start);
        s.enumerate(n - 1, new long[n], 0.0);
        double[] x = new double[n];
        for (int j = 0; j < n; j++) {
            x[j] = lotSizes[j] * s.best[j] + 0.0;
        }
        double[] res = residual(a, b, x);
        double obj = objective(res, weights, ridge, x);
        return new IntegerSolution(s.best.clone(), x, res, obj, contObj, Math.max(0.0, obj - contObj));
    }

    private static double ridgeTerm(double ridge, double[] lotSizes, double[] lots) {
        double s = 0.0;
        for (int j = 0; j < lots.length; j++) {
            double xj = lotSizes[j] * lots[j];
            s += xj * xj;
        }
        return ridge * s;
    }

    static double roundHalfAway(double v) {
        double f = Math.floor(Math.abs(v));
        double r = Math.abs(v) - f >= 0.5 ? f + 1.0 : f;
        return Math.copySign(r, v) + 0.0;
    }

    /** Ellipsoid enumeration around the unconstrained minimiser {@code n*}, with {@code H_L = R'R}. */
    private static final class Search {
        private final double[][] al;
        private final double[] b;
        private final double[] w;
        private final double ridge;
        private final double[] lots;
        private final double[][] r;
        private final double[] centre;
        private final double[] lo;
        private final double[] hi;
        private final double slackFloor;
        long[] best;
        private double bestObj;
        private double radius;

        Search(double[][] al, double[] b, double[] w, double ridge, double[] lots, double[][] hl, double[] cl,
                double[] lo, double[] hi) {
            this.al = al;
            this.b = b;
            this.w = w;
            this.ridge = ridge;
            this.lots = lots;
            this.lo = lo;
            this.hi = hi;
            int n = hl.length;
            double[][] l = Dense.cholesky(hl);
            r = new double[n][n];
            double trace = 0.0;
            for (int i = 0; i < n; i++) {
                trace += hl[i][i];
                for (int j = 0; j < n; j++) {
                    r[i][j] = l[j][i];
                }
            }
            slackFloor = 1e-13 * trace;
            double[] tmp = new double[n]; // n* = -H_L^{-1} c_L by the two triangular solves
            for (int i = 0; i < n; i++) {
                double s = -cl[i];
                for (int k = 0; k < i; k++) {
                    s -= l[i][k] * tmp[k];
                }
                tmp[i] = s / l[i][i];
            }
            centre = new double[n];
            for (int i = n - 1; i >= 0; i--) {
                double s = tmp[i];
                for (int k = i + 1; k < n; k++) {
                    s -= r[i][k] * centre[k];
                }
                centre[i] = s / r[i][i];
            }
        }

        private double quadratic(long[] nn) {
            double q = 0.0;
            for (int i = 0; i < nn.length; i++) {
                double s = 0.0;
                for (int j = i; j < nn.length; j++) {
                    s += r[i][j] * (nn[j] - centre[j]);
                }
                q += s * s;
            }
            return q;
        }

        private double objectiveAt(long[] nn) {
            double[] dn = new double[nn.length];
            for (int j = 0; j < nn.length; j++) {
                dn[j] = nn[j];
            }
            return objective(residual(al, b, dn), w, 0.0, dn) + ridgeTerm(ridge, lots, dn);
        }

        void offer(long[] nn) {
            double obj = objectiveAt(nn);
            if (best == null || better(obj, nn)) {
                best = nn.clone();
                bestObj = obj;
                double q = quadratic(nn);
                radius = q + 1e-9 * (q + Math.abs(obj)) + slackFloor;
            }
        }

        private boolean better(double obj, long[] nn) {
            double tol = 1e-12 * Math.max(Math.abs(obj), Math.abs(bestObj));
            if (obj < bestObj - tol) {
                return true;
            }
            if (obj > bestObj + tol) {
                return false;
            }
            long s1 = 0;
            long s2 = 0;
            for (int j = 0; j < nn.length; j++) {
                s1 += Math.abs(nn[j]);
                s2 += Math.abs(best[j]);
            }
            if (s1 != s2) {
                return s1 < s2;
            }
            for (int j = 0; j < nn.length; j++) {
                if (nn[j] != best[j]) {
                    return nn[j] < best[j];
                }
            }
            return false;
        }

        /** Fixes coordinates {@code i, i-1, ..., 0} given {@code nn[i+1..]} and their partial sum. */
        void enumerate(int i, long[] nn, double partial) {
            if (i < 0) {
                offer(nn);
                return;
            }
            double shift = 0.0;
            for (int j = i + 1; j < nn.length; j++) {
                shift += r[i][j] * (nn[j] - centre[j]);
            }
            double c = centre[i] - shift / r[i][i];
            double rem = radius - partial;
            if (rem < 0.0) {
                return;
            }
            double half = Math.sqrt(rem) / Math.abs(r[i][i]);
            double from = Math.max(lo[i], Math.ceil(c - half));
            double to = Math.min(hi[i], Math.floor(c + half));
            for (double v = from; v <= to; v += 1.0) {
                nn[i] = (long) v;
                double e = r[i][i] * (v - c);
                double next = partial + e * e;
                if (next <= radius) {
                    enumerate(i - 1, nn, next);
                }
            }
            nn[i] = 0;
        }
    }
}
