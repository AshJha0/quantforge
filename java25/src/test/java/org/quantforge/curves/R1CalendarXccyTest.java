package org.quantforge.curves;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Calendars;
import org.quantforge.core.Conventions;
import org.quantforge.core.QfError;

/** Ruling R1-6 (USGS Good Friday early closes) and the cross-currency schedule and input checks. */
class R1CalendarXccyTest {
    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    @Test
    void goodFridayIsABusinessDayOnlyInEarlyCloseYears() {
        for (String d : new String[] {"2007-04-06", "2010-04-02", "2012-04-06", "2015-04-03", "2021-04-02",
                "2023-04-07", "2026-04-03"}) {
            assertTrue(Calendars.isBusinessDay(Calendars.Id.USGS, LocalDate.parse(d)), d);
        }
        for (String d : new String[] {"2024-03-29", "2025-04-18", "2027-03-26"}) {
            assertFalse(Calendars.isBusinessDay(Calendars.Id.USGS, LocalDate.parse(d)), d);
        }
    }

    @Test
    void sofrCompoundingSkipsGoodFridayEvenInAnEarlyCloseYear() {
        // 2026-04-02 (Thu) to 2026-04-06 (Mon): with Good Friday skipped, one SOFR fixing spans four days.
        LocalDate thu = LocalDate.of(2026, 4, 2);
        LocalDate mon = LocalDate.of(2026, 4, 6);
        DatedCompounding.Result r = DatedCompounding.compound(Conventions.SOFR, thu, mon,
                DatedCompounding.Method.NONE, 0, new LocalDate[] {thu}, new double[] {0.036});
        assertEquals(0.036, r.compoundedRate(), 1e-12); // a missing Friday fixing would throw
        assertEquals(4.0 / 360.0, r.accrual(), 1e-15);
    }

    @Test
    void scheduleRollsBackInsideTheMonth() {
        // 2023-12-29 + 3M = 2024-03-29, Good Friday, then Easter Monday: following leaves March, so it goes back.
        assertTrue(Xccy.schedule(LocalDate.of(2023, 12, 29), 3).contains(LocalDate.of(2024, 3, 28)));
    }

    @Test
    void inputChecks() {
        assertEquals("E_INPUT", code(() -> Xccy.checkConventions(Conventions.SONIA, Conventions.ESTR)));
        assertEquals("E_INPUT", code(() -> Xccy.schedule(LocalDate.of(2024, 1, 2), 4)));
        assertEquals("E_INPUT", code(() -> Xccy.schedule(LocalDate.of(2024, 1, 1), 3)));
    }
}
