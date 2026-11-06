package org.quantforge.core;

import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.TemporalAdjusters;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Zone rules written out by hand, instants and cut-offs (timezone-and-cutoff.md). No timezone database. */
public final class TimeZones {
    private TimeZones() {}

    public enum Zone {
        UTC("UTC", 0), LONDON("Europe/London", 0), BERLIN("Europe/Berlin", 3600),
        NEW_YORK("America/New_York", -18000), TOKYO("Asia/Tokyo", 32400);

        final String id;
        final int standard;

        Zone(String id, int standard) {
            this.id = id;
            this.standard = standard;
        }

        public static Zone of(String id) {
            for (Zone z : values()) {
                if (z.id.equals(id)) {
                    return z;
                }
            }
            throw new QfError("E_SCHEMA", "unknown zone " + id, "zone");
        }

        boolean hasSummer() {
            return this == LONDON || this == BERLIN || this == NEW_YORK;
        }
    }

    public enum Overlap { EARLIER, LATER }

    private static final Pattern INSTANT =
            Pattern.compile("(\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2})(Z|[+-]\\d{2}:\\d{2})");
    private static final Pattern LOCAL = Pattern.compile("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}");
    private static final Pattern CUTOFF = Pattern.compile("([01]\\d|2[0-3]):[0-5]\\d");
    private static final DateTimeFormatter FORMAT = DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss");

    private static LocalDateTime dateTime(String text) {
        try {
            return LocalDateTime.of(LocalDate.parse(text.substring(0, 10)), LocalTime.parse(text.substring(11)));
        } catch (DateTimeException e) {
            throw new QfError("E_SCHEMA", "bad date-time " + text);
        }
    }

    /** RFC 3339 instant with whole seconds, as epoch seconds. */
    public static long parseInstant(String text) {
        Matcher m = INSTANT.matcher(text);
        if (!m.matches()) {
            throw new QfError("E_SCHEMA", "bad instant " + text);
        }
        long local = dateTime(m.group(1)).toEpochSecond(ZoneOffset.UTC);
        String off = m.group(2);
        if (off.equals("Z")) {
            return local;
        }
        int hours = Integer.parseInt(off.substring(1, 3));
        int minutes = Integer.parseInt(off.substring(4, 6));
        if (hours > 23 || minutes > 59) {
            throw new QfError("E_SCHEMA", "bad offset in " + text);
        }
        int seconds = hours * 3600 + minutes * 60;
        return off.charAt(0) == '-' ? local + seconds : local - seconds;
    }

    public static LocalDateTime parseLocal(String text) {
        if (!LOCAL.matcher(text).matches()) {
            throw new QfError("E_SCHEMA", "bad local time " + text, "local");
        }
        return dateTime(text);
    }

    public static void checkCutoff(String cutoff) {
        if (!CUTOFF.matcher(cutoff).matches()) {
            throw new QfError("E_SCHEMA", "bad cutoff", "cutoff");
        }
    }

    /** An instant in Z form. */
    public static String formatInstant(long instant) {
        return FORMAT.format(utc(instant)) + "Z";
    }

    private static LocalDateTime utc(long instant) {
        return LocalDateTime.ofEpochSecond(instant, 0, ZoneOffset.UTC);
    }

    private static void checkInstantRange(long instant) {
        int y = utc(instant).getYear();
        if (y < 2007 || y > 2037) {
            throw new QfError("E_DATE_RANGE", "instant outside 2007 to 2037", "instant");
        }
    }

    private static long atUtc(LocalDate d, int hour) {
        return d.atTime(hour, 0).toEpochSecond(ZoneOffset.UTC);
    }

    private static int offsetAt(Zone z, long instant) {
        if (!z.hasSummer()) {
            return z.standard;
        }
        int y = utc(instant).getYear();
        long start;
        long end;
        if (z == Zone.NEW_YORK) {
            start = atUtc(LocalDate.of(y, 3, 1).with(TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.SUNDAY)), 7);
            end = atUtc(LocalDate.of(y, 11, 1).with(TemporalAdjusters.dayOfWeekInMonth(1, DayOfWeek.SUNDAY)), 6);
        } else {
            start = atUtc(LocalDate.of(y, 3, 1).with(TemporalAdjusters.lastInMonth(DayOfWeek.SUNDAY)), 1);
            end = atUtc(LocalDate.of(y, 10, 1).with(TemporalAdjusters.lastInMonth(DayOfWeek.SUNDAY)), 1);
        }
        return instant >= start && instant < end ? z.standard + 3600 : z.standard;
    }

    public static int utcOffset(Zone z, long instant) {
        checkInstantRange(instant);
        return offsetAt(z, instant);
    }

    public static String toLocal(Zone z, long instant) {
        return FORMAT.format(localOf(z, instant));
    }

    private static LocalDateTime localOf(Zone z, long instant) {
        return utc(instant + utcOffset(z, instant));
    }

    /** Returns an instant string in Z form. {@code overlap} may be null. */
    public static String toInstant(Zone z, LocalDateTime local, Overlap overlap) {
        if (local.getYear() < 2007 || local.getYear() > 2037) {
            throw new QfError("E_DATE_RANGE", "local time outside 2007 to 2037", "local");
        }
        long wall = local.toEpochSecond(ZoneOffset.UTC);
        long summer = wall - (z.standard + 3600);
        long standard = wall - z.standard;
        boolean summerFits = z.hasSummer() && offsetAt(z, summer) == z.standard + 3600;
        boolean standardFits = offsetAt(z, standard) == z.standard;
        long instant;
        if (summerFits && standardFits) {
            if (overlap == null) {
                throw new QfError("E_AMBIGUOUS_LOCAL_TIME", "local time occurs twice", "local");
            }
            instant = overlap == Overlap.EARLIER ? summer : standard;
        } else if (summerFits) {
            instant = summer;
        } else if (standardFits) {
            instant = standard;
        } else {
            throw new QfError("E_NONEXISTENT_LOCAL_TIME", "local time falls in a gap", "local");
        }
        return formatInstant(instant);
    }

    public static LocalDate businessDate(long instant, Zone z, String cutoff, Calendars.Id calendar) {
        LocalDateTime local = localOf(z, instant);
        LocalDate date = local.toLocalDate();
        if (!local.toLocalTime().isBefore(LocalTime.parse(cutoff))) {
            date = date.plusDays(1);
        }
        return Calendars.adjust(calendar, date, Calendars.Convention.FOLLOWING);
    }
}
