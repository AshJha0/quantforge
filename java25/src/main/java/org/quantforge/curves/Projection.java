package org.quantforge.curves;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.function.ToDoubleFunction;
import org.quantforge.core.Calendars;
import org.quantforge.core.Conventions;
import org.quantforge.core.DayCount;
import org.quantforge.core.QfError;

/** Term index product models and the projection bootstrap (projection-and-fra.md). */
public final class Projection {
    private Projection() {}

    public enum QuoteType { DEPOSIT, FRA, SWAP }

    /** {@code months} is the deposit or swap length, or the FRA's start. */
    public record Quote(QuoteType type, long months, double rate) {}

    private static final DayCount.Extras NO_EXTRAS = new DayCount.Extras(null, null, null, null, null);

    public static double accrual(Conventions.RateIndex ix, LocalDate s, LocalDate e) {
        return DayCount.yearFraction(ix.dayCount(), s, e, NO_EXTRAS);
    }

    public static LocalDate spot(Conventions.RateIndex ix, LocalDate asOf) {
        return Calendars.addBusinessDays(ix.calendar(), asOf, ix.spotLag());
    }

    /** {@code date} plus months, MODIFIED_FOLLOWING. */
    public static LocalDate plusMonths(Conventions.RateIndex ix, LocalDate date, long months) {
        return Calendars.adjust(ix.calendar(), date.plusMonths(months), Calendars.Convention.MODIFIED_FOLLOWING);
    }

    /** Simple forward on the projection curve. */
    public static double forward(Conventions.RateIndex ix, Curve p, LocalDate s, LocalDate e) {
        return (p.discount(s) / p.discount(e) - 1.0) / accrual(ix, s, e);
    }

    /** The fixed and floating schedules of a swap. */
    public record Swap(Conventions.RateIndex index, List<Schedule.Period> fixed, double[] alpha,
                       List<Schedule.Period> floating) {
        public double annuity(Curve d) {
            double a = 0.0;
            for (int i = 0; i < alpha.length; i++) {
                a += alpha[i] * d.discount(fixed.get(i).end());
            }
            return a;
        }

        public double floatingLeg(Curve d, Curve p) {
            double f = 0.0;
            for (Schedule.Period q : floating) {
                f += (p.discount(q.start()) / p.discount(q.end()) - 1.0) * d.discount(q.end());
            }
            return f;
        }

        public double parRate(Curve d, Curve p) {
            return floatingLeg(d, p) / annuity(d);
        }
    }

    private static void checkMonths(long months, long least) {
        if (months < least || months > 1200) {
            throw new QfError("E_INPUT", "months out of range");
        }
    }

    public static Swap swap(Conventions.RateIndex ix, LocalDate asOf, long months) {
        checkMonths(months, 1);
        LocalDate spot = spot(ix, asOf);
        LocalDate end = spot.plusMonths(months);
        List<Schedule.Period> fixed = Schedule.generate(spot, end, ix.fixedMonths(), ix.calendar(), false, 0);
        List<Schedule.Period> floating = Schedule.generate(spot, end, ix.months(), ix.calendar(), false, 0);
        double[] alpha = new double[fixed.size()];
        for (int i = 0; i < alpha.length; i++) {
            alpha[i] = DayCount.yearFraction(ix.fixedDayCount(), fixed.get(i).start(), fixed.get(i).end(), NO_EXTRAS);
        }
        return new Swap(ix, fixed, alpha, floating);
    }

    public static CurveSolver.Solved bootstrap(Curve discount, Conventions.RateIndex ix, LocalDate asOf,
                                               List<Quote> quotes, Curve.Interpolation interp) {
        if (quotes.isEmpty()) {
            throw new QfError("E_INPUT", "no quotes", "quotes");
        }
        int n = quotes.size();
        LocalDate spot = spot(ix, asOf);
        LocalDate[] dates = new LocalDate[n];
        double[] target = new double[n];
        List<ToDoubleFunction<Curve>> models = new ArrayList<>(n);
        for (int j = 0; j < n; j++) {
            Quote q = quotes.get(j);
            checkMonths(q.months(), q.type() == QuoteType.FRA ? 0 : 1);
            target[j] = q.rate();
            if (q.type() == QuoteType.SWAP) {
                Swap s = swap(ix, asOf, q.months());
                dates[j] = s.fixed().getLast().end();
                models.add(p -> s.parRate(discount, p));
            } else {
                boolean deposit = q.type() == QuoteType.DEPOSIT;
                LocalDate start = deposit ? spot : plusMonths(ix, spot, q.months());
                LocalDate end = plusMonths(ix, start, deposit ? q.months() : ix.months());
                dates[j] = end;
                models.add(p -> forward(ix, p, start, end));
            }
            if (j > 0 && !dates[j].isAfter(dates[j - 1])) {
                throw new QfError("E_INPUT", "quotes are not in pillar order", "quotes");
            }
        }
        return CurveSolver.solve(asOf, interp, dates, target, models, CurveSolver.Method.SEQUENTIAL);
    }

    /** The amount added to an overnight leg to match the term leg, on the quarterly schedule. */
    public static double basisSpread(Curve d, Curve p, Conventions.RateIndex ix, long tenorMonths) {
        checkMonths(tenorMonths, 1);
        LocalDate spot = spot(ix, d.asOf());
        double top = 0.0;
        double bottom = 0.0;
        for (Schedule.Period q : Schedule.generate(spot, spot.plusMonths(tenorMonths), ix.months(), ix.calendar(), false, 0)) {
            double de = d.discount(q.end());
            top += (p.discount(q.start()) / p.discount(q.end()) - d.discount(q.start()) / de) * de;
            bottom += accrual(ix, q.start(), q.end()) * de;
        }
        return top / bottom;
    }
}
