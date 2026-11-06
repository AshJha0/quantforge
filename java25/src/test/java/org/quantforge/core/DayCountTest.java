package org.quantforge.core;

import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class DayCountTest {
    @Test void act360() {
        assertEquals(30.0 / 360.0,
            DayCount.act360(LocalDate.of(2025,1,1), LocalDate.of(2025,1,31)).value(), 1e-14);
    }
    @Test void rejectsReversedDates() {
        assertThrows(IllegalArgumentException.class,
            () -> DayCount.act360(LocalDate.of(2025,2,1), LocalDate.of(2025,1,1)));
    }
}
