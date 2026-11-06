package org.quantforge.curves;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.quantforge.core.Calendars;
import org.quantforge.core.QfError;

/** Regular schedules with one short first stub (schedules.md). */
public final class Schedule {
    private Schedule() {}

    public record Period(LocalDate start, LocalDate end, LocalDate payment) {}

    public static List<Period> generate(LocalDate start, LocalDate end, int frequencyMonths, Calendars.Id cal,
                                        boolean endOfMonth, long paymentLag) {
        if (!end.isAfter(start)) {
            throw new QfError("E_DATE_ORDER", "end is not after start", "end");
        }
        if (paymentLag < 0) {
            throw new QfError("E_INPUT", "payment_lag is negative", "payment_lag");
        }
        List<LocalDate> unadjusted = new ArrayList<>();
        for (long k = 0;; k++) {
            LocalDate d = end.minusMonths(k * frequencyMonths); // From the original end, so the day is clipped once.
            if (!d.isAfter(start)) {
                break;
            }
            unadjusted.add(d);
        }
        Collections.reverse(unadjusted);
        List<Period> periods = new ArrayList<>();
        LocalDate previous = start;
        for (LocalDate d : unadjusted) {
            LocalDate adjusted = endOfMonth
                    ? Calendars.lastBusinessDayOfMonth(cal, YearMonth.from(d))
                    : Calendars.adjust(cal, d, Calendars.Convention.MODIFIED_FOLLOWING);
            if (adjusted.isAfter(previous)) {
                periods.add(new Period(previous, adjusted, Calendars.addBusinessDays(cal, adjusted, paymentLag)));
                previous = adjusted;
            }
        }
        return periods;
    }
}
