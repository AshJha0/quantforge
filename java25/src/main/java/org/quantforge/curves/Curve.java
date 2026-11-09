package org.quantforge.curves;

import org.quantforge.core.Finite;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.function.DoubleUnaryOperator;
import org.quantforge.core.QfError;

/** An immutable discount curve (curve-framework.md). Curve time is always days / 365. */
public final class Curve implements Discounting {
    public enum Interpolation { LOG_LINEAR_DF, LINEAR_ZERO }

    private final LocalDate asOf;
    private final Interpolation interpolation;
    private final LocalDate[] dates;
    private final double[] t;   // t[0] = 0, the implied node at as_of.
    private final double[] lnD; // lnD[0] = 0.
    private final double[] z;   // Zero rates, for LINEAR_ZERO; z[0] = z[1].
    private final Jumps jumps;  // lnD holds ln S = ln D - ln J at the pillars.
    private final DoubleUnaryOperator shift; // Zero-rate shift s(t): D(t) exp(-s(t) t). Null is none.

    private Curve(LocalDate asOf, Interpolation interpolation, LocalDate[] dates, double[] lnDf, Jumps jumps) {
        this.asOf = asOf;
        this.interpolation = interpolation;
        this.dates = dates;
        this.jumps = jumps;
        this.shift = null;
        int n = dates.length;
        t = new double[n + 1];
        lnD = new double[n + 1];
        z = new double[n + 1];
        for (int i = 1; i <= n; i++) {
            t[i] = time(dates[i - 1]);
            lnD[i] = lnDf[i - 1] - jumps.logFactor(dates[i - 1]);
            z[i] = -lnD[i] / t[i];
        }
        z[0] = z[1];
    }

    private Curve(Curve base, DoubleUnaryOperator shift) {
        asOf = base.asOf;
        interpolation = base.interpolation;
        dates = base.dates;
        jumps = base.jumps;
        t = base.t;
        lnD = base.lnD;
        z = base.z;
        this.shift = shift;
    }

    /**
     * This curve with a continuously compounded zero-rate shift {@code s(t)} at every date, interpolation and jumps
     * unchanged (par-and-key-rate.md). Only an unshifted curve can be shifted.
     */
    public Curve withZeroShift(DoubleUnaryOperator s) {
        if (shift != null) {
            throw new IllegalStateException("curve is already shifted");
        }
        return new Curve(this, s);
    }

    public Interpolation interpolation() {
        return interpolation;
    }

    /** Builds from a curve object, with the spec's checks. */
    public static Curve of(LocalDate asOf, Interpolation interpolation, LocalDate[] dates, double[] discountFactors) {
        Finite.check("discountFactors", discountFactors);
        return of(asOf, interpolation, dates, discountFactors, Jumps.NONE);
    }

    /** As {@link #of(LocalDate, Interpolation, LocalDate[], double[])}, with jumps checked after the pillars. */
    public static Curve of(LocalDate asOf, Interpolation interpolation, LocalDate[] dates, double[] discountFactors,
                           Jumps jumps) {
        Finite.check("discountFactors", discountFactors);
        if (dates.length == 0) {
            throw new QfError("E_INPUT", "curve has no pillars");
        }
        LocalDate previous = asOf;
        for (LocalDate d : dates) {
            if (!d.isAfter(previous)) {
                throw new QfError("E_INPUT", "pillar dates must increase from as_of");
            }
            previous = d;
        }
        double[] ln = new double[dates.length];
        for (int i = 0; i < ln.length; i++) {
            if (discountFactors[i] <= 0.0) {
                throw new QfError("E_DOMAIN", "discount factor is not positive");
            }
            ln[i] = Math.log(discountFactors[i]);
        }
        jumps.check(asOf);
        return new Curve(asOf, interpolation, dates, ln, jumps);
    }

    /** Builds from full log discount factors, for solvers. {@code dates} and {@code jumps} are already checked. */
    static Curve fromLogs(LocalDate asOf, Interpolation interpolation, LocalDate[] dates, double[] lnDf, Jumps jumps) {
        return new Curve(asOf, interpolation, dates, lnDf, jumps);
    }

    static Curve fromLogs(LocalDate asOf, Interpolation interpolation, LocalDate[] dates, double[] lnDf) {
        return new Curve(asOf, interpolation, dates, lnDf, Jumps.NONE);
    }

    public Jumps jumps() {
        return jumps;
    }

    public LocalDate asOf() {
        return asOf;
    }

    public LocalDate[] dates() {
        return dates.clone();
    }

    public double[] discountFactors() {
        double[] d = new double[dates.length];
        for (int i = 0; i < d.length; i++) {
            d[i] = Math.exp(lnD[i + 1] - shifted(t[i + 1]) + jumps.logFactor(dates[i]));
        }
        return d;
    }

    public double time(LocalDate d) {
        return ChronoUnit.DAYS.between(asOf, d) / 365.0;
    }

    @Override
    public double discount(LocalDate d) {
        double time = time(d);
        return Math.exp(logDiscount(time) - shifted(time) + jumps.logFactor(d));
    }

    /** -ln(D)/t, or null at as_of. */
    public Double zeroRate(LocalDate d) {
        double time = time(d);
        return time == 0.0 ? null : Double.valueOf(-(logDiscount(time) - shifted(time) + jumps.logFactor(d)) / time);
    }

    /** s(t) t, the log discount the shift removes. */
    private double shifted(double time) {
        return shift == null ? 0.0 : shift.applyAsDouble(time) * time;
    }

    private double logDiscount(double time) {
        if (time < 0.0) {
            throw new QfError("E_OUT_OF_RANGE", "date is before as_of");
        }
        if (time == 0.0) {
            return 0.0;
        }
        int n = t.length - 1;
        if (time >= t[n]) {
            double f = -(lnD[n] - lnD[n - 1]) / (t[n] - t[n - 1]);
            return lnD[n] - f * (time - t[n]);
        }
        int k = Arrays.binarySearch(t, time);
        if (k >= 0) {
            return lnD[k];
        }
        int i = -k - 2;
        double u = (time - t[i]) / (t[i + 1] - t[i]);
        return interpolation == Interpolation.LOG_LINEAR_DF
                ? (1.0 - u) * lnD[i] + u * lnD[i + 1]
                : -((1.0 - u) * z[i] + u * z[i + 1]) * time;
    }
}
