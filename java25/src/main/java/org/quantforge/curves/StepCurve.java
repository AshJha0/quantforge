package org.quantforge.curves;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import org.quantforge.core.QfError;

/** A flat instantaneous forward between meeting dates, with jumps (meeting-steps.md). */
public final class StepCurve implements Discounting {
    private final LocalDate asOf;
    private final double baseRate;
    private final LocalDate[] stepDates;
    private final double[] rates;
    private final Jumps jumps;

    private StepCurve(LocalDate asOf, double baseRate, LocalDate[] stepDates, double[] rates, Jumps jumps) {
        this.asOf = asOf;
        this.baseRate = baseRate;
        this.stepDates = stepDates;
        this.rates = rates;
        this.jumps = jumps;
    }

    /** Step dates strictly increasing and after as_of (E_INPUT, ruling D6), then the jumps' checks. */
    public static void checkSteps(LocalDate asOf, LocalDate[] stepDates) {
        LocalDate previous = asOf;
        for (LocalDate d : stepDates) {
            if (!d.isAfter(previous)) {
                throw new QfError("E_INPUT", "step dates must increase from as_of", "steps");
            }
            previous = d;
        }
    }

    public static StepCurve of(LocalDate asOf, double baseRate, LocalDate[] stepDates, double[] rates, Jumps jumps) {
        checkSteps(asOf, stepDates);
        jumps.check(asOf);
        return new StepCurve(asOf, baseRate, stepDates, rates, jumps);
    }

    /** For solvers: inputs already checked. */
    static StepCurve unchecked(LocalDate asOf, double baseRate, LocalDate[] stepDates, double[] rates, Jumps jumps) {
        return new StepCurve(asOf, baseRate, stepDates, rates, jumps);
    }

    private long days(LocalDate d) {
        long n = ChronoUnit.DAYS.between(asOf, d);
        if (n < 0) {
            throw new QfError("E_OUT_OF_RANGE", "date is before as_of", "dates");
        }
        return n;
    }

    @Override
    public double discount(LocalDate d) {
        long n = days(d);
        double integral = 0.0; // In rate-days.
        long from = 0;
        double rate = baseRate;
        for (int k = 0; k < stepDates.length; k++) {
            long at = ChronoUnit.DAYS.between(asOf, stepDates[k]);
            if (at >= n) {
                break;
            }
            integral += rate * (at - from);
            from = at;
            rate = rates[k];
        }
        integral += rate * (n - from);
        return Math.exp(-integral / 365.0 + jumps.logFactor(d));
    }

    /** The forward in force on {@code d}: a step takes effect on its date. */
    public double forward(LocalDate d) {
        days(d);
        double rate = baseRate;
        for (int k = 0; k < stepDates.length && !stepDates[k].isAfter(d); k++) {
            rate = rates[k];
        }
        return rate;
    }
}
