package org.quantforge.curves;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.function.ToDoubleFunction;
import org.quantforge.core.Calendars;
import org.quantforge.core.Conventions;
import org.quantforge.core.QfError;

/** Cross-currency basis and NDFs (cross-currency.md, rulings D17, D18). */
public final class Xccy {
    private Xccy() {}

    private static boolean joint(LocalDate d) {
        return Calendars.isBusinessDay(Calendars.Id.USGS, d) && Calendars.isBusinessDay(Calendars.Id.EUTA, d);
    }

    /** USD domestic, EUR foreign only (ruling D17). */
    public static void checkConventions(Conventions.RateIndex domestic, Conventions.RateIndex foreign) {
        if (domestic != Conventions.SOFR || foreign != Conventions.ESTR) {
            throw new QfError("E_INPUT", "domestic must be SOFR and foreign ESTR", "domestic_convention");
        }
    }

    /** Period ends, MODIFIED_FOLLOWING on the joint calendar; element 0 is start. */
    public static List<LocalDate> schedule(LocalDate start, long months) {
        Calendars.checkRange(start);
        if (!joint(start)) {
            throw new QfError("E_INPUT", "start is not a joint business day", "start");
        }
        if (months <= 0 || months % 3 != 0 || months > 1200) {
            throw new QfError("E_INPUT", "months must be a positive multiple of 3", "months");
        }
        List<LocalDate> out = new ArrayList<>();
        out.add(start);
        for (long k = 1; k <= months / 3; k++) {
            LocalDate raw = start.plusMonths(3 * k);
            LocalDate d = raw;
            while (!joint(d)) {
                d = d.plusDays(1);
            }
            if (d.getMonth() != raw.getMonth()) {
                d = raw;
                while (!joint(d)) {
                    d = d.minusDays(1);
                }
            }
            out.add(d);
        }
        return out;
    }

    /** The leg with exchanges, per unit notional. */
    public static double leg(List<LocalDate> dates, Discounting p, Discounting d, double m) {
        double sum = 0.0;
        for (int i = 1; i < dates.size(); i++) {
            LocalDate s = dates.get(i - 1);
            LocalDate e = dates.get(i);
            double alpha = java.time.temporal.ChronoUnit.DAYS.between(s, e) / 360.0;
            sum += (p.discount(s) / p.discount(e) - 1.0 + m * alpha) * d.discount(e);
        }
        return sum + d.discount(dates.getLast()) - d.discount(dates.getFirst());
    }

    public static CurveSolver.Solved bootstrap(Curve domestic, Curve foreignProjection, LocalDate start, long[] months,
                                               double[] spreads, Curve.Interpolation interp) {
        if (months.length == 0) {
            throw new QfError("E_INPUT", "no quotes", "quotes");
        }
        for (int j = 1; j < months.length; j++) {
            if (months[j] <= months[j - 1]) {
                throw new QfError("E_INPUT", "months must increase", "quotes");
            }
        }
        LocalDate[] pillars = new LocalDate[months.length];
        List<ToDoubleFunction<Curve>> models = new ArrayList<>();
        for (int j = 0; j < months.length; j++) {
            List<LocalDate> dates = schedule(start, months[j]);
            pillars[j] = dates.getLast();
            double m = spreads[j];
            models.add(c -> leg(dates, foreignProjection, c, m));
        }
        if (start.isBefore(domestic.asOf())) {
            throw new QfError("E_OUT_OF_RANGE", "start is before as_of", "start");
        }
        return CurveSolver.solve(domestic.asOf(), interp, pillars, new double[months.length], models,
                CurveSolver.Method.SEQUENTIAL);
    }

    public record Pv(double pv, double foreignLeg, double domesticLeg) {}

    public static Pv pv(Curve domestic, Curve fProj, Curve fDisc, double spot, LocalDate start, long months,
                        double notional, double spread, boolean receiveForeign) {
        if (!(spot > 0.0)) {
            throw new QfError("E_DOMAIN", "spot must be positive", "spot");
        }
        if (start.isBefore(domestic.asOf())) {
            throw new QfError("E_OUT_OF_RANGE", "start is before as_of", "start");
        }
        List<LocalDate> dates = schedule(start, months);
        double f = notional * leg(dates, fProj, fDisc, spread);
        double d = notional * spot * leg(dates, domestic, domestic, 0.0);
        return new Pv((receiveForeign ? 1.0 : -1.0) * (spot * f - d), f, d);
    }

    public record Ndf(double pv, double forward) {}

    public static Ndf ndf(Curve usd, Curve off, double spot, LocalDate fixingDate, LocalDate payment, double strike,
                          double notional, boolean buy, Double fixing) {
        if (payment.isBefore(fixingDate)) {
            throw new QfError("E_DATE_ORDER", "payment_date is before fixing_date", "payment_date");
        }
        if (!fixingDate.isAfter(usd.asOf()) && fixing == null) {
            throw new QfError("E_INPUT", "a past fixing must be given", "fixing");
        }
        if (!(spot > 0.0) || !(strike > 0.0) || (fixing != null && !(fixing > 0.0))) {
            throw new QfError("E_DOMAIN", "spot, fixing and strike must be positive");
        }
        double dUsd = usd.discount(payment);
        double f = fixing != null ? fixing : spot * dUsd / off.discount(payment);
        return new Ndf((buy ? 1.0 : -1.0) * notional * (1.0 - strike / f) * dUsd, f);
    }
}
