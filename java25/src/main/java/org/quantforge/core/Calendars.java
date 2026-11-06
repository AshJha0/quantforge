package org.quantforge.core;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

/** Holiday calendars and business-day rules (calendars.md). */
public final class Calendars {
    private Calendars() {}

    public enum Id { GBLO, EUTA, USGS }

    public enum Convention { UNADJUSTED, FOLLOWING, PRECEDING, MODIFIED_FOLLOWING, MODIFIED_PRECEDING }

    private static final Pattern TENOR = Pattern.compile("[1-9][0-9]{0,3}[DWMY]");
    /** A pure memo of the rules: it cannot change any result. */
    private static final Map<Integer, TreeSet<LocalDate>> CACHE = new ConcurrentHashMap<>();

    public static void checkRange(LocalDate d) {
        if (d.getYear() < 2000 || d.getYear() > 2099) {
            throw new QfError("E_DATE_RANGE", "date outside 2000 to 2099: " + d);
        }
    }

    public static LocalDate easter(int y) {
        int a = y % 19, b = y / 100, c = y % 100, d = b / 4, e = b % 4, f = (b + 8) / 25, g = (b - f + 1) / 3;
        int h = (19 * a + b - d - g + 15) % 30, i = c / 4, k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7;
        int m = (a + 11 * h + 22 * l) / 451;
        int n = h + l - 7 * m + 114;
        return LocalDate.of(y, n / 31, n % 31 + 1);
    }

    private static LocalDate nth(int y, int month, DayOfWeek dow, int n) {
        return LocalDate.of(y, month, 1).with(TemporalAdjusters.dayOfWeekInMonth(n, dow));
    }

    private static LocalDate last(int y, int month, DayOfWeek dow) {
        return LocalDate.of(y, month, 1).with(TemporalAdjusters.lastInMonth(dow));
    }

    private static boolean weekend(LocalDate d) {
        return d.getDayOfWeek() == DayOfWeek.SATURDAY || d.getDayOfWeek() == DayOfWeek.SUNDAY;
    }

    /** Friday if a Saturday, Monday if a Sunday. */
    private static LocalDate nearest(LocalDate d) {
        return switch (d.getDayOfWeek()) {
            case SATURDAY -> d.minusDays(1);
            case SUNDAY -> d.plusDays(1);
            default -> d;
        };
    }

    private static void gblo(int y, List<LocalDate> out) {
        LocalDate ny = LocalDate.of(y, 1, 1);
        out.add(weekend(ny) ? ny.with(TemporalAdjusters.next(DayOfWeek.MONDAY)) : ny);
        LocalDate easter = easter(y);
        out.add(easter.minusDays(2));
        out.add(easter.plusDays(1));
        out.add(y == 2020 ? LocalDate.of(2020, 5, 8) : nth(y, 5, DayOfWeek.MONDAY, 1));
        out.add(switch (y) {
            case 2002 -> LocalDate.of(2002, 6, 4);
            case 2012 -> LocalDate.of(2012, 6, 4);
            case 2022 -> LocalDate.of(2022, 6, 2);
            default -> last(y, 5, DayOfWeek.MONDAY);
        });
        out.add(last(y, 8, DayOfWeek.MONDAY));
        int[] days = switch (LocalDate.of(y, 12, 25).getDayOfWeek()) {
            case SATURDAY -> new int[] {27, 28};
            case SUNDAY -> new int[] {26, 27};
            case FRIDAY -> new int[] {25, 28};
            default -> new int[] {25, 26};
        };
        out.add(LocalDate.of(y, 12, days[0]));
        out.add(LocalDate.of(y, 12, days[1]));
        for (String d : List.of("2002-06-03", "2011-04-29", "2012-06-05", "2022-06-03", "2022-09-19", "2023-05-08")) {
            addIfYear(y, d, out);
        }
    }

    private static void euta(int y, List<LocalDate> out) {
        LocalDate easter = easter(y);
        out.add(LocalDate.of(y, 1, 1));
        out.add(easter.minusDays(2));
        out.add(easter.plusDays(1));
        out.add(LocalDate.of(y, 5, 1));
        out.add(LocalDate.of(y, 12, 25));
        out.add(LocalDate.of(y, 12, 26));
        addIfYear(y, "2001-12-31", out);
    }

    private static void usgs(int y, List<LocalDate> out) {
        LocalDate ny = LocalDate.of(y, 1, 1);
        out.add(ny.getDayOfWeek() == DayOfWeek.SUNDAY ? ny.plusDays(1) : ny);
        out.add(nth(y, 1, DayOfWeek.MONDAY, 3));
        out.add(nth(y, 2, DayOfWeek.MONDAY, 3));
        out.add(easter(y).minusDays(2));
        out.add(last(y, 5, DayOfWeek.MONDAY));
        if (y >= 2022) {
            out.add(nearest(LocalDate.of(y, 6, 19)));
        }
        out.add(nearest(LocalDate.of(y, 7, 4)));
        out.add(nth(y, 9, DayOfWeek.MONDAY, 1));
        out.add(nth(y, 10, DayOfWeek.MONDAY, 2));
        LocalDate vets = LocalDate.of(y, 11, 11);
        out.add(vets.getDayOfWeek() == DayOfWeek.SUNDAY ? vets.plusDays(1) : vets);
        out.add(nth(y, 11, DayOfWeek.THURSDAY, 4));
        out.add(nearest(LocalDate.of(y, 12, 25)));
        for (String d : List.of("2004-06-11", "2012-10-30", "2018-12-05")) {
            addIfYear(y, d, out);
        }
    }

    private static void addIfYear(int y, String date, List<LocalDate> out) {
        LocalDate d = LocalDate.parse(date);
        if (d.getYear() == y) {
            out.add(d);
        }
    }

    private static TreeSet<LocalDate> weekdayHolidays(Id cal, int year) {
        return CACHE.computeIfAbsent(cal.ordinal() * 10000 + year, key -> {
            List<LocalDate> all = new ArrayList<>();
            switch (cal) {
                case GBLO -> gblo(year, all);
                case EUTA -> euta(year, all);
                case USGS -> usgs(year, all);
            }
            TreeSet<LocalDate> set = new TreeSet<>();
            for (LocalDate d : all) {
                if (!weekend(d)) {
                    set.add(d);
                }
            }
            return set;
        });
    }

    public static List<LocalDate> holidays(Id cal, long year) {
        if (year < 2000 || year > 2099) {
            throw new QfError("E_DATE_RANGE", "year outside 2000 to 2099", "year");
        }
        return List.copyOf(weekdayHolidays(cal, (int) year));
    }

    public static boolean isBusinessDay(Id cal, LocalDate d) {
        checkRange(d);
        return !weekend(d) && !weekdayHolidays(cal, d.getYear()).contains(d);
    }

    private static LocalDate roll(Id cal, LocalDate d, int step) {
        while (!isBusinessDay(cal, d)) {
            d = d.plusDays(step);
        }
        return d;
    }

    public static LocalDate adjust(Id cal, LocalDate d, Convention c) {
        checkRange(d);
        return switch (c) {
            case UNADJUSTED -> d;
            case FOLLOWING -> roll(cal, d, 1);
            case PRECEDING -> roll(cal, d, -1);
            case MODIFIED_FOLLOWING -> {
                LocalDate r = roll(cal, d, 1);
                yield r.getMonth() == d.getMonth() ? r : roll(cal, d, -1);
            }
            case MODIFIED_PRECEDING -> {
                LocalDate r = roll(cal, d, -1);
                yield r.getMonth() == d.getMonth() ? r : roll(cal, d, 1);
            }
        };
    }

    public static LocalDate addBusinessDays(Id cal, LocalDate d, long days) {
        checkRange(d);
        if (days == 0) {
            return roll(cal, d, 1);
        }
        int step = days > 0 ? 1 : -1;
        long left = Math.abs(days);
        while (left > 0) {
            d = d.plusDays(step);
            if (isBusinessDay(cal, d)) {
                left--;
            }
        }
        return d;
    }

    /** Count in [start, end). */
    public static long businessDaysBetween(Id cal, LocalDate start, LocalDate end) {
        checkRange(start);
        checkRange(end);
        if (end.isBefore(start)) {
            throw new QfError("E_DATE_ORDER", "end is before start", "end");
        }
        long n = 0;
        for (LocalDate d = start; d.isBefore(end); d = d.plusDays(1)) {
            if (isBusinessDay(cal, d)) {
                n++;
            }
        }
        return n;
    }

    private static LocalDate lastBusinessDayOfMonth(Id cal, YearMonth ym) {
        return roll(cal, ym.atEndOfMonth(), -1);
    }

    public static LocalDate addTenor(Id cal, LocalDate date, String tenor, Convention c, boolean endOfMonth) {
        if (!TENOR.matcher(tenor).matches()) {
            throw new QfError("E_SCHEMA", "bad tenor", "tenor");
        }
        checkRange(date);
        int n = Integer.parseInt(tenor.substring(0, tenor.length() - 1));
        char unit = tenor.charAt(tenor.length() - 1);
        if (unit == 'D' || unit == 'W') {
            return adjust(cal, date.plusDays(unit == 'W' ? 7L * n : n), c);
        }
        LocalDate target = date.plusMonths(unit == 'Y' ? 12L * n : n); // Clamps to the month's last day.
        checkRange(target);
        if (endOfMonth && date.equals(lastBusinessDayOfMonth(cal, YearMonth.from(date)))) {
            return lastBusinessDayOfMonth(cal, YearMonth.from(target));
        }
        return adjust(cal, target, c);
    }
}
