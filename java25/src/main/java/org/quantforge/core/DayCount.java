package org.quantforge.core;

import java.time.LocalDate;
import java.time.Month;
import java.time.Year;
import java.time.temporal.ChronoUnit;

/** Year fractions (daycount.md). */
public final class DayCount {
    private DayCount() {}

    public enum Convention {
        ACT_360, ACT_365F, ACT_364, ACT_365_25, NL_365, ONE_ONE, BUS_252, ACT_365L, ACT_ACT_ISDA, ACT_ACT_ICMA,
        ACT_ACT_AFB, THIRTY_360_BOND, THIRTY_360_US, THIRTY_E_360, THIRTY_E_360_ISDA, THIRTY_E_PLUS_360
    }

    /** Conditional inputs. Each convention reads only the ones it needs; the caller has checked they exist. */
    public record Extras(Integer frequency, LocalDate refStart, LocalDate refEnd, LocalDate termination,
                         Calendars.Id calendar) {}

    private static long between(LocalDate a, LocalDate b) {
        return ChronoUnit.DAYS.between(a, b);
    }

    private static int daysInYear(int y) {
        return Year.isLeap(y) ? 366 : 365;
    }

    private static boolean eofeb(LocalDate d) {
        return d.getMonth() == Month.FEBRUARY && d.getDayOfMonth() == d.lengthOfMonth();
    }

    /** Number of 29 Februaries in [from, to], both ends included. */
    private static int leapDays(LocalDate from, LocalDate to) {
        int n = 0;
        for (int y = from.getYear(); y <= to.getYear(); y++) {
            if (Year.isLeap(y)) {
                LocalDate d = LocalDate.of(y, 2, 29);
                if (!d.isBefore(from) && !d.isAfter(to)) {
                    n++;
                }
            }
        }
        return n;
    }

    public static double yearFraction(Convention c, LocalDate start, LocalDate end, Extras x) {
        if (end.isBefore(start)) {
            throw new QfError("E_DATE_ORDER", "end is before start", "end");
        }
        if (c == Convention.ACT_ACT_ICMA
                && (!x.refEnd().isAfter(x.refStart()) || start.isBefore(x.refStart()) || end.isAfter(x.refEnd()))) {
            throw new QfError("E_INPUT", "accrual must lie inside one reference period");
        }
        if (c == Convention.BUS_252) {
            Calendars.checkRange(start);
            Calendars.checkRange(end);
        }
        if (start.equals(end)) {
            return 0.0; // Also guards 30E+/360 and German 30/360, whose adjustments alone would not give 0.
        }
        long days = between(start, end);
        return switch (c) {
            case ACT_360 -> days / 360.0;
            case ACT_365F -> days / 365.0;
            case ACT_364 -> days / 364.0;
            case ACT_365_25 -> days / 365.25;
            case NL_365 -> (days - leapDays(start.plusDays(1), end)) / 365.0;
            case ONE_ONE -> 1.0;
            case BUS_252 -> Calendars.businessDaysBetween(x.calendar(), start, end) / 252.0;
            case ACT_365L -> {
                if (x.frequency() == 1) {
                    yield days / (leapDays(start.plusDays(1), end) > 0 ? 366.0 : 365.0);
                }
                yield days / (double) daysInYear(end.getYear());
            }
            case ACT_ACT_ISDA -> isda(start, end, days);
            case ACT_ACT_ICMA -> days / ((double) x.frequency() * between(x.refStart(), x.refEnd()));
            case ACT_ACT_AFB -> afb(start, end);
            default -> thirty(c, start, end, x);
        };
    }

    private static double isda(LocalDate start, LocalDate end, long days) {
        int y1 = start.getYear();
        int y2 = end.getYear();
        if (y1 == y2) {
            return days / (double) daysInYear(y1);
        }
        return between(start, LocalDate.of(y1 + 1, 1, 1)) / (double) daysInYear(y1) + (y2 - y1 - 1)
                + between(LocalDate.of(y2, 1, 1), end) / (double) daysInYear(y2);
    }

    private static LocalDate back(LocalDate end, int n) {
        if (n == 0) {
            return end;
        }
        int y = end.getYear() - n;
        if (end.getMonth() == Month.FEBRUARY) {
            if (end.getDayOfMonth() == 28 && Year.isLeap(y)) {
                return LocalDate.of(y, 2, 29);
            }
            if (end.getDayOfMonth() == 29 && !Year.isLeap(y)) {
                return LocalDate.of(y, 2, 28);
            }
        }
        return LocalDate.of(y, end.getMonth(), end.getDayOfMonth());
    }

    private static double afb(LocalDate start, LocalDate end) {
        int n = 0;
        while (!back(end, n + 1).isBefore(start)) {
            n++;
        }
        LocalDate e = back(end, n);
        if (e.equals(start)) {
            return n;
        }
        double d = leapDays(start, e.minusDays(1)) > 0 ? 366.0 : 365.0;
        return n + between(start, e) / d;
    }

    private static double thirty(Convention c, LocalDate start, LocalDate end, Extras x) {
        int d1 = start.getDayOfMonth();
        int d2 = end.getDayOfMonth();
        int m2 = end.getMonthValue();
        switch (c) {
            case THIRTY_360_BOND -> {
                if (d1 == 31) {
                    d1 = 30;
                }
                if (d2 == 31 && d1 == 30) {
                    d2 = 30;
                }
            }
            case THIRTY_360_US -> {
                if (eofeb(start) && eofeb(end)) {
                    d2 = 30;
                }
                if (eofeb(start)) {
                    d1 = 30;
                }
                if (d2 == 31 && d1 >= 30) {
                    d2 = 30;
                }
                if (d1 == 31) {
                    d1 = 30;
                }
            }
            case THIRTY_E_360 -> {
                if (d1 == 31) {
                    d1 = 30;
                }
                if (d2 == 31) {
                    d2 = 30;
                }
            }
            case THIRTY_E_360_ISDA -> {
                if (d1 == 31 || eofeb(start)) {
                    d1 = 30;
                }
                if (d2 == 31 || (eofeb(end) && !end.equals(x.termination()))) {
                    d2 = 30;
                }
            }
            case THIRTY_E_PLUS_360 -> {
                if (d1 == 31) {
                    d1 = 30;
                }
                if (d2 == 31) {
                    d2 = 1;
                    m2 += 1;
                }
            }
            default -> throw new IllegalArgumentException(c.name());
        }
        int num = 360 * (end.getYear() - start.getYear()) + 30 * (m2 - start.getMonthValue()) + (d2 - d1);
        return num / 360.0;
    }
}
