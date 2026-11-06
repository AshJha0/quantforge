package org.quantforge.curves;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;
import java.util.function.ToDoubleFunction;
import java.util.regex.Pattern;
import org.quantforge.core.Calendars;
import org.quantforge.core.Conventions;
import org.quantforge.core.DayCount;
import org.quantforge.core.QfError;

/** OIS product model and bootstrap (ois-curves.md). */
public final class Ois {
    private Ois() {}

    /** A quote as given: a rate, or a bid and ask. */
    public record Quote(String tenor, Double rate, Double bid, Double ask) {
        double mid() {
            return rate != null ? rate : (bid + ask) / 2.0;
        }

        boolean crossed() {
            return rate == null && bid > ask;
        }
    }

    /** The shared periods of both legs, with fixed accruals. */
    public record Legs(List<Schedule.Period> periods, double[] alpha) {
        public double annuity(Curve d) {
            double a = 0.0;
            for (int i = 0; i < alpha.length; i++) {
                a += alpha[i] * d.discount(periods.get(i).payment());
            }
            return a;
        }

        /** The general form. The telescoped form is wrong under a payment lag. */
        public double floating(Curve d) {
            double f = 0.0;
            for (Schedule.Period p : periods) {
                f += (d.discount(p.start()) / d.discount(p.end()) - 1.0) * d.discount(p.payment());
            }
            return f;
        }

        public double parRate(Curve d) {
            return floating(d) / annuity(d);
        }
    }

    private static final Pattern TENOR = Pattern.compile("[1-9][0-9]{0,3}[DWMY]");
    private static final DayCount.Extras NO_EXTRAS = new DayCount.Extras(null, null, null, null, null);

    public static void checkTenor(String tenor) {
        if (!TENOR.matcher(tenor).matches()) {
            throw new QfError("E_SCHEMA", "bad tenor " + tenor, "tenor");
        }
    }

    public static LocalDate spot(Conventions.RateIndex c, LocalDate asOf) {
        LocalDate adjusted = Calendars.adjust(c.calendar(), asOf, Calendars.Convention.FOLLOWING);
        return Calendars.addBusinessDays(c.calendar(), adjusted, c.spotLag());
    }

    public static Legs legs(Conventions.RateIndex c, LocalDate asOf, String tenor) {
        checkTenor(tenor);
        LocalDate spot = spot(c, asOf);
        int n = Integer.parseInt(tenor.substring(0, tenor.length() - 1));
        char unit = tenor.charAt(tenor.length() - 1);
        long months = unit == 'Y' ? 12L * n : n;
        List<Schedule.Period> periods;
        if (unit == 'D' || unit == 'W' || months <= c.fixedMonths()) {
            LocalDate end = Calendars.addTenor(c.calendar(), spot, tenor, Calendars.Convention.MODIFIED_FOLLOWING, true);
            periods = List.of(new Schedule.Period(spot, end,
                    Calendars.addBusinessDays(c.calendar(), end, c.paymentLag())));
        } else {
            boolean eom = !spot.isBefore(Calendars.lastBusinessDayOfMonth(c.calendar(), YearMonth.from(spot)));
            periods = Schedule.generate(spot, spot.plusMonths(months), c.fixedMonths(), c.calendar(), eom, c.paymentLag());
        }
        double[] alpha = new double[periods.size()];
        for (int i = 0; i < alpha.length; i++) {
            Schedule.Period p = periods.get(i);
            alpha[i] = DayCount.yearFraction(c.fixedDayCount(), p.start(), p.end(), NO_EXTRAS);
        }
        return new Legs(periods, alpha);
    }

    /** Builds a curve from quotes; {@code bump} is added to each quote's mid, and may be null. */
    public static CurveSolver.Solved bootstrap(Conventions.RateIndex c, LocalDate asOf, List<Quote> quotes,
                                               Curve.Interpolation interp, CurveSolver.Method method, double[] bump) {
        if (quotes.isEmpty()) {
            throw new QfError("E_INPUT", "no quotes", "quotes");
        }
        int n = quotes.size();
        LocalDate[] dates = new LocalDate[n];
        List<ToDoubleFunction<Curve>> models = new ArrayList<>(n);
        double[] target = new double[n];
        for (int j = 0; j < n; j++) {
            Legs legs = legs(c, asOf, quotes.get(j).tenor());
            dates[j] = legs.periods().getLast().payment();
            models.add(legs::parRate);
            if (j > 0 && !dates[j].isAfter(dates[j - 1])) {
                throw new QfError("E_INPUT", "pillars not strictly increasing", "quotes");
            }
        }
        for (int j = 0; j < n; j++) {
            if (quotes.get(j).crossed()) {
                throw new QfError("E_INPUT", "bid is above ask", "quotes");
            }
            target[j] = quotes.get(j).mid() + (bump == null ? 0.0 : bump[j]);
        }
        return CurveSolver.solve(asOf, interp, dates, target, models, method);
    }

    /** Compounded in arrears from actual fixings. */
    public static double compound(double[] rates, long[] days, int denominator) {
        if (rates.length != days.length || rates.length == 0) {
            throw new QfError("E_INPUT", "need equal, non-empty rates and days");
        }
        double product = 1.0;
        double total = 0.0;
        for (int i = 0; i < days.length; i++) {
            if (days[i] < 1) {
                throw new QfError("E_INPUT", "days must be at least 1", "days");
            }
            product *= 1.0 + rates[i] * days[i] / denominator;
            total += days[i];
        }
        return (product - 1.0) * denominator / total;
    }
}
