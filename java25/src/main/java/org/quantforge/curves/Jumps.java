package org.quantforge.curves;

import java.time.LocalDate;
import org.quantforge.core.QfError;

/**
 * Discount jumps (curve-framework.md, ruling D2): {@code J(d)} is the product of the factors dated strictly
 * before {@code d}.
 */
public record Jumps(LocalDate[] dates, double[] factors) {
    public static final Jumps NONE = new Jumps(new LocalDate[0], new double[0]);

    /** Dates strictly increasing and after as_of (E_INPUT), then factors positive (E_DOMAIN). */
    public void check(LocalDate asOf) {
        LocalDate previous = asOf;
        for (LocalDate d : dates) {
            if (!d.isAfter(previous)) {
                throw new QfError("E_INPUT", "jump dates must increase from as_of", "jumps");
            }
            previous = d;
        }
        for (double f : factors) {
            if (!(f > 0.0) || Double.isInfinite(f)) {
                throw new QfError("E_DOMAIN", "jump factor must be positive", "jumps");
            }
        }
    }

    /** ln J(d). Zero with no jumps. */
    public double logFactor(LocalDate d) {
        double s = 0.0;
        for (int i = 0; i < dates.length && dates[i].isBefore(d); i++) {
            s += Math.log(factors[i]);
        }
        return s;
    }
}
