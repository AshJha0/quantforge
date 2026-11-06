package org.quantforge.core;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** The market convention registry (conventions.md). */
public final class Conventions {
    private Conventions() {}

    /** An overnight or term rate index. {@code months} is 0 for overnight. */
    public record RateIndex(String id, boolean overnight, String currency, DayCount.Convention dayCount,
                            Calendars.Id calendar, int spotLag, int paymentLag, int months, int fixedMonths,
                            DayCount.Convention fixedDayCount) {}

    public record FxPair(String id, String base, String quote, int spotLag, List<Calendars.Id> calendars, double pip) {}

    public static final RateIndex SONIA = new RateIndex("SONIA", true, "GBP", DayCount.Convention.ACT_365F,
            Calendars.Id.GBLO, 0, 0, 0, 12, DayCount.Convention.ACT_365F);
    public static final RateIndex SOFR = new RateIndex("SOFR", true, "USD", DayCount.Convention.ACT_360,
            Calendars.Id.USGS, 2, 2, 0, 12, DayCount.Convention.ACT_360);
    public static final RateIndex USD_TERM_3M = new RateIndex("USD-TERM-3M", false, "USD", DayCount.Convention.ACT_360,
            Calendars.Id.USGS, 2, 0, 3, 12, DayCount.Convention.THIRTY_360_BOND);
    public static final FxPair GBPUSD = new FxPair("GBPUSD", "GBP", "USD", 2,
            List.of(Calendars.Id.GBLO, Calendars.Id.USGS), 0.0001);
    public static final FxPair EURUSD = new FxPair("EURUSD", "EUR", "USD", 2,
            List.of(Calendars.Id.EUTA, Calendars.Id.USGS), 0.0001);

    private static QfError unknown(String id) {
        return new QfError("E_SCHEMA", "unknown convention " + id);
    }

    public static RateIndex overnight(String id) {
        return switch (id) {
            case "SONIA" -> SONIA;
            case "SOFR" -> SOFR;
            default -> throw unknown(id);
        };
    }

    public static RateIndex term(String id) {
        if (id.equals(USD_TERM_3M.id())) {
            return USD_TERM_3M;
        }
        throw unknown(id);
    }

    public static FxPair pair(String id) {
        return switch (id) {
            case "GBPUSD" -> GBPUSD;
            case "EURUSD" -> EURUSD;
            default -> throw unknown(id);
        };
    }

    private static Map<String, Object> rateRecord(RateIndex c) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("kind", c.overnight() ? "OVERNIGHT" : "TERM");
        m.put("currency", c.currency());
        m.put("day_count", c.dayCount().name());
        m.put("calendar", c.calendar().name());
        m.put("spot_lag", c.spotLag());
        if (c.overnight()) {
            m.put("payment_lag", c.paymentLag());
        } else {
            m.put("months", c.months());
        }
        m.put("fixed_months", c.fixedMonths());
        m.put("fixed_day_count", c.fixedDayCount().name());
        m.put("business_day_convention", "MODIFIED_FOLLOWING");
        return m;
    }

    private static Map<String, Object> pairRecord(FxPair p) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("kind", "FX");
        m.put("base", p.base());
        m.put("quote", p.quote());
        m.put("spot_lag", p.spotLag());
        m.put("calendars", p.calendars().stream().map(Enum::name).toList());
        m.put("pip", p.pip());
        return m;
    }

    public static Map<String, Object> lookup(String id) {
        return switch (id) {
            case "SONIA" -> rateRecord(SONIA);
            case "SOFR" -> rateRecord(SOFR);
            case "USD-TERM-3M" -> rateRecord(USD_TERM_3M);
            case "GBPUSD" -> pairRecord(GBPUSD);
            case "EURUSD" -> pairRecord(EURUSD);
            default -> throw unknown(id);
        };
    }
}
