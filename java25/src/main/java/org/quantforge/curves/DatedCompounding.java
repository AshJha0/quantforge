package org.quantforge.curves;

import org.quantforge.core.Finite;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.quantforge.core.Calendars;
import org.quantforge.core.Conventions;
import org.quantforge.core.DayCount;
import org.quantforge.core.QfError;

/** Overnight compounding by date, and ISDA IBOR fallbacks (overnight-compounding.md). */
public final class DatedCompounding {
    private DatedCompounding() {}

    public enum Method { NONE, LOOKBACK, OBSERVATION_SHIFT, LOCKOUT }

    public record Result(double compoundedRate, double accrual, double interest) {}

    public record Fallback(Conventions.RateIndex index, double spread) {}

    /** The eight IBORs and their ISDA spread adjustments of 2021-03-05 (ruling D8). Others are E_SCHEMA. */
    public static Fallback fallback(String ibor) {
        return switch (ibor) {
            case "USD-LIBOR-1M" -> new Fallback(Conventions.SOFR, 0.0011448);
            case "USD-LIBOR-3M" -> new Fallback(Conventions.SOFR, 0.0026161);
            case "USD-LIBOR-6M" -> new Fallback(Conventions.SOFR, 0.0042826);
            case "USD-LIBOR-12M" -> new Fallback(Conventions.SOFR, 0.0071513);
            case "GBP-LIBOR-1M" -> new Fallback(Conventions.SONIA, 0.0003260);
            case "GBP-LIBOR-3M" -> new Fallback(Conventions.SONIA, 0.0011930);
            case "GBP-LIBOR-6M" -> new Fallback(Conventions.SONIA, 0.0027660);
            case "GBP-LIBOR-12M" -> new Fallback(Conventions.SONIA, 0.0046440);
            default -> throw new QfError("E_SCHEMA", "unknown ibor " + ibor, "ibor");
        };
    }

    private static int denominator(Conventions.RateIndex c) {
        return c.dayCount() == DayCount.Convention.ACT_360 ? 360 : 365;
    }

    /**
     * A business day of the index's compounding calendar. For SOFR that is USGS with every Good Friday closed, since
     * the New York Fed publishes no SOFR then, even in USGS early-close years (ruling R1-6).
     */
    private static boolean open(Conventions.RateIndex c, LocalDate d) {
        if (c == Conventions.SOFR && d.equals(Calendars.easter(d.getYear()).minusDays(2))) {
            return false;
        }
        return Calendars.isBusinessDay(c.calendar(), d);
    }

    /** {@code d} moved {@code k} business days earlier, inside the calendar's range. */
    private static LocalDate back(Conventions.RateIndex c, LocalDate d, long k) {
        LocalDate x = d;
        for (long left = k; left > 0; ) {
            x = x.minusDays(1);
            Calendars.checkRange(x);
            if (open(c, x)) {
                left--;
            }
        }
        return x;
    }

    public static Result compound(Conventions.RateIndex c, LocalDate start, LocalDate end, Method method, long k,
                                  LocalDate[] fixingDates, double[] fixingRates) {
        Finite.check("fixingRates", fixingRates);
        if (!end.isAfter(start)) {
            throw new QfError("E_DATE_ORDER", "end is not after start", "end");
        }
        Calendars.checkRange(start);
        Calendars.checkRange(end);
        List<LocalDate> days = new ArrayList<>();
        for (LocalDate d = start; !d.isAfter(end); d = d.plusDays(1)) {
            if (open(c, d) || d.equals(start) || d.equals(end)) {
                days.add(d);
            }
        }
        int n = days.size() - 1;
        if (k < 0 || (method == Method.NONE && k != 0) || (method == Method.LOCKOUT && (k < 1 || k > n - 1))) {
            throw new QfError("E_INPUT", "shift_days not allowed for " + method, "shift_days");
        }
        if (!open(c, start) || !open(c, end)) {
            throw new QfError("E_INPUT", "start and end must be business days", "start");
        }
        Map<LocalDate, Double> fixings = new HashMap<>();
        for (int i = 0; i < fixingDates.length; i++) {
            if (fixings.put(fixingDates[i], fixingRates[i]) != null) {
                throw new QfError("E_INPUT", "two fixings on " + fixingDates[i], "fixings");
            }
        }
        LocalDate[] obs = new LocalDate[n + 1];
        for (int i = 0; i <= n; i++) {
            obs[i] = method == Method.LOOKBACK || method == Method.OBSERVATION_SHIFT ? back(c, days.get(i), k) : days.get(i);
        }
        int b = denominator(c);
        double growth = 1.0;
        long total = 0;
        for (int i = 0; i < n; i++) {
            LocalDate fixingDate = method == Method.LOCKOUT && i >= n - k ? days.get((int) (n - k)) : obs[i];
            Double r = fixings.get(fixingDate);
            if (r == null) {
                throw new QfError("E_INPUT", "missing fixing for " + fixingDate, "fixings");
            }
            long w = method == Method.OBSERVATION_SHIFT
                    ? ChronoUnit.DAYS.between(obs[i], obs[i + 1])
                    : ChronoUnit.DAYS.between(days.get(i), days.get(i + 1));
            growth *= 1.0 + r * w / b;
            total += w;
        }
        double rate = (growth - 1.0) * b / total;
        double accrual = ChronoUnit.DAYS.between(start, end) / (double) b;
        return new Result(rate, accrual, rate * accrual);
    }
}
