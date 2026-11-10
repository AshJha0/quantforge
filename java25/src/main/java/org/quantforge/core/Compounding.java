package org.quantforge.core;

/**
 * Rate and discount-factor conversion (compounding.md). Conversions go through ln(1/D) with log1p and
 * expm1, which equals the table's formulas and keeps precision for short times.
 */
public final class Compounding {
    private Compounding() {}

    public enum Kind { SIMPLE, PERIODIC, CONTINUOUS }

    /** {@code frequency} is used only by PERIODIC. */
    public record Basis(Kind kind, int frequency) {}

    private static void checkDomain(double r, double t, Basis b) {
        if (b.kind() == Kind.SIMPLE && 1.0 + r * t <= 0.0) {
            throw new QfError("E_DOMAIN", "1 + r t must be positive");
        }
        if (b.kind() == Kind.PERIODIC && 1.0 + r / b.frequency() <= 0.0) {
            throw new QfError("E_DOMAIN", "1 + r/n must be positive");
        }
    }

    /** -ln D(r, t). */
    private static double logInverse(double r, double t, Basis b) {
        return switch (b.kind()) {
            case SIMPLE -> Math.log1p(r * t);
            case PERIODIC -> b.frequency() * t * Math.log1p(r / b.frequency());
            case CONTINUOUS -> r * t;
        };
    }

    public static double discountFactor(double r, double t, Basis b) {
        Finite.check("r", r);
        Finite.check("t", t);
        if (t < 0.0) {
            throw new QfError("E_DOMAIN", "t is negative", "t");
        }
        checkDomain(r, t, b);
        return b.kind() == Kind.SIMPLE ? 1.0 / (1.0 + r * t) : Math.exp(-logInverse(r, t, b));
    }

    public static double convert(double r, double t, Basis from, Basis to) {
        Finite.check("r", r);
        Finite.check("t", t);
        if (t <= 0.0) {
            throw new QfError("E_DOMAIN", "t must be positive", "t");
        }
        checkDomain(r, t, from);
        double l = logInverse(r, t, from);
        return switch (to.kind()) {
            case SIMPLE -> Math.expm1(l) / t;
            case PERIODIC -> to.frequency() * Math.expm1(l / (to.frequency() * t));
            case CONTINUOUS -> l / t;
        };
    }
}
