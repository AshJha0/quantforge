package org.quantforge.core;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

public final class DayCount {
    private DayCount() {}

    private static long days(LocalDate start, LocalDate end) {
        if (end.isBefore(start)) throw new IllegalArgumentException("end date precedes start date");
        return ChronoUnit.DAYS.between(start, end);
    }

    public static YearFraction act360(LocalDate start, LocalDate end) {
        return new YearFraction(days(start, end) / 360.0, "ACT/360");
    }

    public static YearFraction act365f(LocalDate start, LocalDate end) {
        return new YearFraction(days(start, end) / 365.0, "ACT/365F");
    }
}
