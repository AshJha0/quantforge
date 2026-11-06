package org.quantforge.core;

public record YearFraction(double value, String convention) {
    public YearFraction {
        if (!Double.isFinite(value) || value < 0.0) {
            throw new IllegalArgumentException("year fraction must be finite and non-negative");
        }
    }
}
