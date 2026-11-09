package org.quantforge.core;

/**
 * Rule E1: every public numeric input is finite. NaN slips past comparisons such as {@code vol < 0}, so each public
 * entry point checks its reals here first and reports NaN, +inf and -inf as {@code E_DOMAIN}. Negative zero is finite
 * and passes. Raw kernels that skip this check say so in their own documentation.
 */
public final class Finite {
    private Finite() {}

    private static QfError fault(String name) {
        return new QfError("E_DOMAIN", name + " must be finite", name);
    }

    public static void check(String name, double v) {
        if (!Double.isFinite(v)) {
            throw fault(name);
        }
    }

    /** A null array is left to the caller's own null rule. */
    public static void check(String name, double[] v) {
        if (v == null) {
            return;
        }
        for (double x : v) {
            check(name, x);
        }
    }

    public static void check(String name, double[][] v) {
        if (v == null) {
            return;
        }
        for (double[] row : v) {
            check(name, row);
        }
    }
}
