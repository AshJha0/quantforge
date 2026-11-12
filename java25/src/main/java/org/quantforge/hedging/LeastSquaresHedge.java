package org.quantforge.hedging;

import java.util.ArrayList;
import java.util.List;
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
     * @param risk weighted squared residual plus the ridge term, null without cost inputs (ruling I-27)
     * @param cost {@code C(x)}, null without cost inputs
     * @param margin {@code sum_j margin_rates_j |x_j|}, null without margin inputs
     */
    public record Solution(double[] x, double[] residual, double objective, int rank, Double risk, Double cost,
            Double margin) {
        /**
         * A wave 1 answer, without the cost outputs.
         *
         * @param x positions
         * @param residual {@code A x + b}
         * @param objective {@code f(x)}
         * @param rank reduced-Hessian rank
         */
        public Solution(double[] x, double[] residual, double objective, int rank) {
            this(x, residual, objective, rank, null, null, null);
        }
    }

    /**
     * The wave 4a cost inputs of {@code hedge.qp.solve} ({@code hedge-costs-and-frontier.md}); each array may be null
     * when not given. The cost is {@code C(x) = sum_j (half_spreads_j |x_j| + impact_j x_j^2)}, weighted by
     * {@code costWeight}, and {@code sum_j margin_rates_j |x_j| <= marginLimit} is a constraint.
     *
     * @param halfSpreads cost per unit traded, each {@code >= 0}, or null
     * @param impact linear-impact coefficients, each {@code >= 0}, or null
     * @param costWeight weight of the cost against the risk, {@code >= 0}
     * @param marginRates margin per unit held, each {@code >= 0}, or null
     * @param marginLimit the margin cap, {@code >= 0}, or null
     */
    public record Costs(double[] halfSpreads, double[] impact, double costWeight, double[] marginRates,
            Double marginLimit) {}

    /** Relative slack in the subgradient test at a kink before a sign is flipped. */
    private static final double KINK_TOL = 1e-9;

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
        return solve(a, b, weights, ridge, eqMatrix, eqRhs, lower, upper, minNorm, null);
    }

    private static void costLength(double[] v, int n, String key) {
        if (v != null && v.length != n) {
            throw input(key);
        }
    }

    private static void nonNegative(double[] v, String key) {
        if (v != null) {
            for (double x : v) {
                if (!(x >= 0.0)) {
                    throw domain(key);
                }
            }
        }
    }

    /**
     * Solves {@code hedge.qp.solve} with the optional wave 4a costs. The {@code |x|} terms are handled exactly by
     * solving the strictly convex problem on each closed sign orthant of the instruments that carry them, where the
     * spread cost and the margin are linear, and keeping the best; an instrument whose cost exceeds its benefit lands
     * on its orthant's bound and is returned as exactly 0.
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
     * @param costs the cost inputs, or null when none is given
     * @return the unique minimiser, with {@code risk}, {@code cost} and {@code margin} when costs are given
     * @throws QfError {@code E_INPUT}, {@code E_DOMAIN}, {@code E_SINGULAR} or {@code E_INFEASIBLE},
     *     in the specification's order
     */
    public static Solution solve(double[][] a, double[] b, double[] weights, double ridge, double[][] eqMatrix,
            double[] eqRhs, double[] lower, double[] upper, boolean minNorm, Costs costs) {
        return solve(a, b, weights, ridge, eqMatrix, eqRhs, lower, upper, minNorm, costs, false);
    }

    /** Test oracle only: {@link #solve} with the {@code 2^k} sign-orthant enumeration in place of the sign search. */
    static Solution solveByEnumeration(double[][] a, double[] b, double[] weights, double ridge, double[][] eqMatrix,
            double[] eqRhs, double[] lower, double[] upper, Costs costs) {
        return solve(a, b, weights, ridge, eqMatrix, eqRhs, lower, upper, false, costs, true);
    }

    private static Solution solve(double[][] a, double[] b, double[] weights, double ridge, double[][] eqMatrix,
            double[] eqRhs, double[] lower, double[] upper, boolean minNorm, Costs costs, boolean enumerate) {
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
        double[] spreads = new double[n];
        double[] impact = new double[n];
        double[] rates = null;
        double cw = 0.0;
        if (costs != null) { // ruling I-25
            costLength(costs.halfSpreads(), n, "half_spreads");
            costLength(costs.impact(), n, "impact");
            costLength(costs.marginRates(), n, "margin_rates");
            if ((costs.marginRates() == null) != (costs.marginLimit() == null)) {
                throw input(costs.marginRates() == null ? "margin_limit" : "margin_rates");
            }
            if (minNorm) {
                throw new QfError("E_INPUT", "MIN_NORM does not take cost inputs", "singular");
            }
            nonNegative(costs.halfSpreads(), "half_spreads");
            nonNegative(costs.impact(), "impact");
            nonNegative(costs.marginRates(), "margin_rates");
            if (!(costs.costWeight() >= 0.0)) {
                throw domain("cost_weight");
            }
            if (costs.marginLimit() != null && !(costs.marginLimit() >= 0.0)) {
                throw domain("margin_limit");
            }
            cw = costs.costWeight();
            if (costs.halfSpreads() != null) {
                spreads = costs.halfSpreads();
            }
            if (costs.impact() != null) {
                impact = costs.impact();
            }
            rates = costs.marginRates();
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
        for (int j = 0; j < n; j++) {
            h[j][j] += cw * impact[j]; // ruling I-26: impact counts like a ridge
        }
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
        if (costs != null) {
            Reduced rd = new Reduced(hr, z, xp, hxp, c, k);
            CostTerms ct = new CostTerms(cw, spreads, impact, rates, costs.marginLimit());
            double[] x = enumerate ? costSearchByEnumeration(rd, lo, hi, ct, a, b, weights, ridge)
                    : costSearch(rd, lo, hi, ct, a, b, weights, ridge);
            double[] res = residual(a, b, x);
            double risk = objective(res, weights, ridge, x);
            double cost = 0.0;
            for (int j = 0; j < n; j++) {
                cost += spreads[j] * Math.abs(x[j]) + impact[j] * x[j] * x[j];
            }
            Double margin = null;
            if (rates != null) {
                double mg = 0.0;
                for (int j = 0; j < n; j++) {
                    mg += rates[j] * Math.abs(x[j]);
                }
                margin = mg;
            }
            return new Solution(x, res, risk + cw * cost, rank, risk, cost, margin);
        }
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
            y = boundedReduced(hr, gr, z, xp, lo, hi, activeLo, activeHi, null, 0.0);
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

    /** The reduced problem's fixed parts: {@code Z'HZ}, {@code Z}, {@code x_p}, {@code H x_p}, {@code c}, {@code k}. */
    private record Reduced(double[][] hr, double[][] z, double[] xp, double[] hxp, double[] c, int k) {}

    /** The cost inputs as the solver sees them; {@code rates} and {@code marginLimit} are null without a margin. */
    private record CostTerms(double cw, double[] spreads, double[] impact, double[] rates, Double marginLimit) {
        /** True when instrument {@code j} has an {@code |x_j|} term, in the objective or in the margin. */
        boolean costly(int j) {
            return (cw > 0.0 && spreads[j] > 0.0) || (rates != null && rates[j] > 0.0);
        }
    }

    /**
     * One orthant's solution: {@code x}, the true objective, and the multipliers (in the solver's half-scaled units)
     * of each instrument's lower and upper bound and of the margin row.
     */
    private record OrthantSolution(double[] x, double f, double[] muLo, double[] muHi, double muRow) {}

    /**
     * Solves the strictly convex problem on the closed orthant {@code signs} ({@code +1}, {@code -1}, or 0 for an
     * instrument without an {@code |x|} term), where {@code |x_j| = s_j x_j}: the spread cost adds
     * {@code cw h_j s_j / 2} to {@code c_j}, the margin is one linear row, and the orthant is the bound
     * {@code s_j x_j >= 0}. Returns null when the orthant is empty or infeasible.
     */
    private static OrthantSolution orthant(Reduced rd, double[] lo, double[] hi, int[] signs, CostTerms ct,
            double[][] a, double[] b, double[] w, double ridge) {
        int n = lo.length;
        int r = rd.hr().length;
        double[] l2 = lo.clone();
        double[] h2 = hi.clone();
        double[] grad = new double[n];
        double[] row = ct.rates() == null ? null : new double[n];
        for (int j = 0; j < n; j++) {
            grad[j] = rd.hxp()[j] + rd.c()[j];
            if (signs[j] > 0) {
                l2[j] = Math.max(l2[j], 0.0);
            } else if (signs[j] < 0) {
                h2[j] = Math.min(h2[j], 0.0);
            }
            if (l2[j] > h2[j]) {
                return null;
            }
            grad[j] += 0.5 * ct.cw() * ct.spreads()[j] * signs[j];
            if (row != null) {
                row[j] = ct.rates()[j] * signs[j];
            }
        }
        double[] gr = Dense.mulT(rd.z(), grad, r);
        boolean[] actLo = new boolean[n];
        boolean[] actHi = new boolean[n];
        double[] muLo = new double[n];
        double[] muHi = new double[n];
        double[] muRow = new double[1];
        double[] y;
        try {
            y = boundedReduced(rd.hr(), gr, rd.z(), rd.xp(), l2, h2, actLo, actHi, row,
                    ct.marginLimit() == null ? 0.0 : ct.marginLimit(), muLo, muHi, muRow);
        } catch (QfError e) {
            if (e.code().equals("E_INFEASIBLE")) {
                return null;
            }
            throw e;
        }
        double[] x = new double[n];
        for (int j = 0; j < n; j++) {
            double v = rd.xp()[j];
            for (int t = 0; t < r; t++) {
                v += rd.z()[j][t] * y[t];
            }
            if ((actLo[j] && (rd.k() == 0 || l2[j] == 0.0)) || (actHi[j] && (rd.k() == 0 || h2[j] == 0.0))) {
                v = actLo[j] ? l2[j] : h2[j]; // the exact bound, so an exact 0 at an orthant's kink
            }
            x[j] = v + 0.0;
        }
        return new OrthantSolution(x, trueObjective(x, ct, a, b, w, ridge), muLo, muHi, muRow[0]);
    }

    private static double trueObjective(double[] x, CostTerms ct, double[][] a, double[] b, double[] w,
            double ridge) {
        double f = objective(residual(a, b, x), w, ridge, x);
        for (int j = 0; j < x.length; j++) {
            f += ct.cw() * (ct.spreads()[j] * Math.abs(x[j]) + ct.impact()[j] * x[j] * x[j]);
        }
        return f;
    }

    /**
     * Test oracle only: the best solution over every closed sign orthant of the instruments with an {@code |x|} term,
     * {@code 2^k} problems. {@link #costSearch} must return the same minimiser.
     */
    private static double[] costSearchByEnumeration(Reduced rd, double[] lo, double[] hi, CostTerms ct, double[][] a,
            double[] b, double[] w, double ridge) {
        int n = lo.length;
        List<Integer> costly = new ArrayList<>();
        for (int j = 0; j < n; j++) {
            if (ct.costly(j)) {
                costly.add(j);
            }
        }
        OrthantSolution best = null;
        for (long mask = 0; mask < (1L << costly.size()); mask++) {
            int[] signs = new int[n];
            for (int i = 0; i < costly.size(); i++) {
                signs[costly.get(i)] = ((mask >> i) & 1L) == 0 ? 1 : -1;
            }
            OrthantSolution o = orthant(rd, lo, hi, signs, ct, a, b, w, ridge);
            if (o != null && (best == null || o.f() < best.f())) {
                best = o;
            }
        }
        if (best == null) {
            throw new QfError("E_INFEASIBLE", "no point satisfies the bounds, equalities and margin limit");
        }
        return best.x();
    }

    /** The sign of a starting point, choosing a non-empty orthant for a coordinate at 0. */
    private static int[] signsOf(double[] x, double[] lo, double[] hi, CostTerms ct) {
        int[] signs = new int[x.length];
        for (int j = 0; j < x.length; j++) {
            if (ct.costly(j)) {
                signs[j] = x[j] > 0.0 || (x[j] == 0.0 && hi[j] > 0.0) ? 1 : -1;
            }
        }
        return signs;
    }

    /**
     * The exact minimiser by a sign-state active-set method (ruling I-48: no size limit below the I-4 one). Each step
     * solves the strictly convex problem on one closed sign orthant. At the orthant's optimum, an instrument at 0 whose
     * orthant-bound multiplier {@code nu_j} exceeds {@code 2 (cw h_j / 2 + mu m_j)} breaks the subgradient condition
     * {@code |g_j| <= cw h_j + mu m_j}; its sign is flipped, which keeps the current point feasible and lets the
     * objective fall. When no instrument breaks the condition, the KKT conditions of the whole problem hold, so the
     * point is the unique minimiser. A step that flips several signs and does not lower the objective is retried
     * with the single worst one; the objective falls at every accepted step, so no orthant is visited twice.
     *
     * <p>With a margin limit, the start must be a feasible orthant: a phase 1 minimises the smooth part plus a
     * heavily weighted margin, and refuses ({@code E_INFEASIBLE}) when even that point is above the limit.
     */
    private static double[] costSearch(Reduced rd, double[] lo, double[] hi, CostTerms ct, double[][] a, double[] b,
            double[] w, double ridge) {
        int n = lo.length;
        CostTerms smooth = new CostTerms(0.0, new double[n], ct.impact(), null, null);
        OrthantSolution free = orthant(rd, lo, hi, new int[n], smooth, a, b, w, ridge);
        if (free == null) {
            throw new QfError("E_INFEASIBLE", "no point satisfies the bounds and equalities");
        }
        int[] signs = signsOf(free.x(), lo, hi, ct);
        if (ct.rates() != null) {
            OrthantSolution start = orthant(rd, lo, hi, signs, ct, a, b, w, ridge);
            if (start == null) {
                // Phase 1: the least-margin point, as the minimiser of the smooth part plus a dominant margin cost.
                double weight = 1e12 * Math.max(1.0, free.f());
                double[] mr = ct.rates();
                CostTerms phase1 = new CostTerms(weight, mr, ct.impact(), null, null);
                double[] x1 = signSearch(rd, lo, hi, signsOf(free.x(), lo, hi, phase1), phase1, a, b, w, ridge).x();
                double margin = 0.0;
                for (int j = 0; j < n; j++) {
                    margin += mr[j] * Math.abs(x1[j]);
                }
                if (margin > ct.marginLimit() + 1e-9 * Math.max(1.0, ct.marginLimit())) {
                    throw new QfError("E_INFEASIBLE", "no point meets the margin limit");
                }
                signs = signsOf(x1, lo, hi, ct);
            }
        }
        return signSearch(rd, lo, hi, signs, ct, a, b, w, ridge).x();
    }

    private static OrthantSolution signSearch(Reduced rd, double[] lo, double[] hi, int[] start, CostTerms ct,
            double[][] a, double[] b, double[] w, double ridge) {
        int n = lo.length;
        int[] signs = start.clone();
        OrthantSolution cur = orthant(rd, lo, hi, signs, ct, a, b, w, ridge);
        if (cur == null) {
            throw new QfError("E_INFEASIBLE", "no point satisfies the bounds, equalities and margin limit");
        }
        for (int iter = 0; iter < 4 * n + 100; iter++) {
            List<Integer> broken = new ArrayList<>();
            int worst = -1;
            double worstExcess = 0.0;
            for (int j = 0; j < n; j++) {
                if (signs[j] == 0 || cur.x()[j] != 0.0) {
                    continue;
                }
                boolean otherSideOpen = signs[j] > 0 ? lo[j] < 0.0 : hi[j] > 0.0;
                if (!otherSideOpen) {
                    continue;
                }
                double nu = signs[j] > 0 ? cur.muLo()[j] : cur.muHi()[j];
                double rate = ct.rates() == null ? 0.0 : ct.rates()[j];
                double allowed = 2.0 * (0.5 * ct.cw() * ct.spreads()[j] + cur.muRow() * rate);
                double excess = nu - allowed * (1.0 + KINK_TOL);
                if (excess > 1e-14 * Math.max(1.0, nu)) {
                    broken.add(j);
                    if (excess > worstExcess) {
                        worstExcess = excess;
                        worst = j;
                    }
                }
            }
            if (broken.isEmpty()) {
                return cur;
            }
            int[] next = signs.clone();
            for (int j : broken) {
                next[j] = -next[j];
            }
            OrthantSolution cand = orthant(rd, lo, hi, next, ct, a, b, w, ridge);
            if ((cand == null || !(cand.f() < cur.f())) && broken.size() > 1) {
                next = signs.clone();
                next[worst] = -next[worst];
                cand = orthant(rd, lo, hi, next, ct, a, b, w, ridge);
            }
            if (cand == null || !(cand.f() < cur.f())) {
                return cur; // degenerate: the flip cannot lower the objective, so the point is already optimal
            }
            signs = next;
            cur = cand;
        }
        throw new QfError("E_NO_CONVERGENCE", "sign-state iterations exhausted");
    }

    /**
     * The bounded reduced problem in {@code y}, with {@code x = x_p + Z y}, and an optional general row
     * {@code row . x <= limit}; marks the active bounds.
     */
    private static double[] boundedReduced(double[][] hr, double[] gr, double[][] z, double[] xp, double[] lo,
            double[] hi, boolean[] activeLo, boolean[] activeHi, double[] row, double limit) {
        return boundedReduced(hr, gr, z, xp, lo, hi, activeLo, activeHi, row, limit, new double[xp.length],
                new double[xp.length], new double[1]);
    }

    /** As above, and writes each bound's and the row's multiplier (0 when inactive). */
    private static double[] boundedReduced(double[][] hr, double[] gr, double[][] z, double[] xp, double[] lo,
            double[] hi, boolean[] activeLo, boolean[] activeHi, double[] row, double limit, double[] muLo,
            double[] muHi, double[] muRow) {
        int n = xp.length;
        int r = hr.length;
        int count = row == null ? 0 : 1;
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
            if (row != null && Dense.dot(row, xp) > limit + 1e-10 * Math.max(1.0, limit)) {
                throw new QfError("E_INFEASIBLE", "the equalities fix a point above the margin limit");
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
        if (row != null) {
            cons[at] = new double[r];
            for (int t = 0; t < r; t++) {
                for (int j = 0; j < n; j++) {
                    cons[at][t] -= row[j] * z[j][t];
                }
            }
            rhs[at] = Dense.dot(row, xp) - limit;
            which[at++] = 0;
        }
        DualActiveSet.Result res = DualActiveSet.solve(hr, gr, cons, rhs);
        for (int i = 0; i < count; i++) {
            if (which[i] > 0) {
                muLo[which[i] - 1] = res.multipliers()[i];
            } else if (which[i] < 0) {
                muHi[-which[i] - 1] = res.multipliers()[i];
            } else {
                muRow[0] = res.multipliers()[i];
            }
            if (res.active()[i] && which[i] != 0) {
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
        double[] nc = boundedReduced(hl, cl, identity, new double[n], lo, hi, actLo, actHi, null, 0.0);
        for (int j = 0; j < n; j++) {
            nc[j] = actLo[j] ? lo[j] : actHi[j] ? hi[j] : nc[j];
            if (Math.abs(nc[j]) > 0x1p52) { // ruling I-49: integers beyond 2^52 are not all representable
                throw new QfError("E_LIMIT", "a relaxed lot count is above 2^52", "lot_sizes");
            }
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
