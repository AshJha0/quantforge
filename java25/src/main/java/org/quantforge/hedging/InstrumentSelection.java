package org.quantforge.hedging;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.quantforge.core.QfError;

/**
 * {@code hedge.select.solve} ({@code 08-hedging/instrument-selection.md}): the best hedge using at most {@code K} of
 * the instruments. Every subset of 1 to {@code K} instruments is solved by {@link LeastSquaresHedge#solve} on its
 * columns, in order of size and then of index list, and a later subset replaces the best only when its objective is
 * lower by more than {@code 1e-12} relative, which is the tie rule of ruling I-34.
 */
public final class InstrumentSelection {
    private InstrumentSelection() {}

    /** Ruling I-35: at most 20 instruments. */
    public static final int MAX_INSTRUMENTS = 20;

    /** Ruling I-53: at most 100,000 candidate subsets. */
    public static final long MAX_SUBSETS = 100_000;

    /**
     * The number of candidate subsets, {@code sum_{k=1..min(K,n)} C(n, k)} (ruling I-53); 0 when {@code K < 1}.
     *
     * @param n the number of instruments
     * @param maxInstruments {@code K}
     * @return the subset count, saturating at {@link Long#MAX_VALUE}
     */
    public static long candidateSubsets(int n, long maxInstruments) {
        long total = 0;
        long c = 1;
        for (int k = 1; k <= Math.min(maxInstruments, n); k++) {
            c = c * (n - k + 1) / k; // C(n, k) from C(n, k-1), exact for n <= 62
            total += c;
            if (total < 0 || n > 62) {
                return Long.MAX_VALUE;
            }
        }
        return total;
    }

    /**
     * The answer.
     *
     * @param selected chosen 0-based indices, ascending
     * @param x positions, 0 outside {@code selected}
     * @param residual {@code A x + b}
     * @param objective {@code f(x)}
     */
    public record Selection(int[] selected, double[] x, double[] residual, double objective) {}

    private static double[] pick(double[] v, int[] idx) {
        if (v == null) {
            return null;
        }
        double[] out = new double[idx.length];
        for (int i = 0; i < idx.length; i++) {
            out[i] = v[idx[i]];
        }
        return out;
    }

    /**
     * Solves the selection.
     *
     * @param a factor-by-instrument sensitivities, {@code m x n}, {@code n <= 20}
     * @param b the book's factor exposures
     * @param weights factor weights, each {@code > 0}
     * @param ridge Tikhonov weight, {@code >= 0}
     * @param lower lower bounds (infinite for none), or null; each must admit 0
     * @param upper upper bounds (infinite for none), or null; each must admit 0
     * @param maxInstruments {@code K}, in {@code 1..n}
     * @param withEqualitiesOrPolicy true when {@code eq_matrix}, {@code eq_rhs} or {@code singular} was given
     * @return the best subset and its hedge
     * @throws QfError {@code E_INPUT}, {@code E_DOMAIN} or {@code E_SINGULAR}, in the specification's order
     */
    public static Selection select(double[][] a, double[] b, double[] weights, double ridge, double[] lower,
            double[] upper, long maxInstruments, boolean withEqualitiesOrPolicy) {
        // hedge.qp.solve checks 1 to 3 on the full problem; it is regular or singular, never infeasible here.
        int n = a.length == 0 ? 0 : a[0].length;
        try {
            LeastSquaresHedge.solve(a, b, weights, ridge, null, null, lower, upper, false);
        } catch (QfError e) {
            if (e.code().equals("E_INPUT") || e.code().equals("E_DOMAIN")) {
                throw e;
            }
        }
        if (maxInstruments < 1 || maxInstruments > n) {
            throw new QfError("E_INPUT", "max_instruments outside 1..n", "max_instruments");
        }
        if (withEqualitiesOrPolicy) {
            throw new QfError("E_INPUT", "selection takes no equalities or singular policy", "eq_matrix");
        }
        for (int j = 0; j < n; j++) {
            if ((lower != null && lower[j] > 0.0) || (upper != null && upper[j] < 0.0)) {
                throw new QfError("E_DOMAIN", "a bound excludes 0", lower != null && lower[j] > 0.0 ? "lower" : "upper");
            }
        }
        Dense.Eigen e = Dense.eigen(Dense.gram(a, weights, ridge, n));
        double min = Double.POSITIVE_INFINITY;
        for (double v : e.values()) {
            min = Math.min(min, v);
        }
        if (!(min > Dense.RANK_TOL * e.maxAbs())) {
            throw new QfError("E_SINGULAR", "the full hedge problem is singular", "a");
        }
        int[] best = null;
        LeastSquaresHedge.Solution bestSol = null;
        for (int size = 1; size <= maxInstruments; size++) {
            for (int[] idx : combinations(n, size)) {
                double[][] sub = new double[a.length][];
                for (int i = 0; i < a.length; i++) {
                    sub[i] = pick(a[i], idx);
                }
                LeastSquaresHedge.Solution s = LeastSquaresHedge.solve(sub, b, weights, ridge, null, null,
                        pick(lower, idx), pick(upper, idx), false);
                if (bestSol == null || s.objective() < bestSol.objective()
                        - 1e-12 * Math.max(Math.abs(s.objective()), Math.abs(bestSol.objective()))) {
                    best = idx;
                    bestSol = s;
                }
            }
        }
        double[] x = new double[n];
        for (int i = 0; i < best.length; i++) {
            x[best[i]] = bestSol.x()[i];
        }
        return new Selection(best, x, bestSol.residual(), bestSol.objective());
    }

    /** The {@code size}-subsets of {@code 0..n-1} in lexicographic order. */
    static List<int[]> combinations(int n, int size) {
        List<int[]> out = new ArrayList<>();
        int[] c = new int[size];
        for (int i = 0; i < size; i++) {
            c[i] = i;
        }
        while (true) {
            out.add(Arrays.copyOf(c, size));
            int i = size - 1;
            while (i >= 0 && c[i] == n - size + i) {
                i--;
            }
            if (i < 0) {
                return out;
            }
            c[i]++;
            for (int j = i + 1; j < size; j++) {
                c[j] = c[j - 1] + 1;
            }
        }
    }
}
