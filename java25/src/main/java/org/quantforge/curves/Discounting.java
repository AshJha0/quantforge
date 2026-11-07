package org.quantforge.curves;

import java.time.LocalDate;

/** Anything that gives a discount factor for a date: a pillar curve or a step curve. */
public interface Discounting {
    double discount(LocalDate d);
}
