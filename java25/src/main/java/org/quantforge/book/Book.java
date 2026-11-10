package org.quantforge.book;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.quantforge.core.Finite;
import org.quantforge.core.QfError;

/** Trade and position lifecycle, end-of-day marks (book-lifecycle.md, ruling F-34). */
public final class Book {
    private Book() {}

    public enum EventType { TRADE, FIXING, EXPIRY, DEFAULT, ROLL }

    /** An event as given; fields its type does not use are null. */
    public record Event(LocalDate date, EventType type, String instrument, Double quantity, Double price,
                        String index, Double value, String from, String to, Double fromPrice, Double toPrice) {}

    public record Position(String instrument, double quantity, double averageCost) {}

    public record Fixing(String index, LocalDate date, double value) {}

    public record Lifecycle(List<Position> positions, Map<String, Double> realized, double totalRealized,
                            List<Fixing> fixings) {}

    private static final class Pos {
        double q;
        double a;
    }

    public static Lifecycle apply(List<Position> opening, List<Event> events) {
        TreeMap<String, Pos> book = new TreeMap<>();
        for (Position p : opening) {
            Finite.check("quantity", p.quantity());
            Finite.check("average_cost", p.averageCost());
            if (book.containsKey(p.instrument())) {
                throw new QfError("E_INPUT", "duplicate opening position " + p.instrument(), "positions");
            }
            if (p.quantity() != 0.0) {
                Pos x = new Pos();
                x.q = p.quantity();
                x.a = p.averageCost();
                book.put(p.instrument(), x);
            }
        }
        for (int i = 1; i < events.size(); i++) {
            if (events.get(i).date().isBefore(events.get(i - 1).date())) {
                throw new QfError("E_INPUT", "events are not in date order", "events");
            }
        }
        TreeMap<String, Double> realized = new TreeMap<>();
        Set<String> closed = new HashSet<>();
        Map<String, Map<LocalDate, Double>> fixings = new TreeMap<>();
        for (Event e : events) {
            switch (e.type()) {
                case TRADE -> {
                    if (e.quantity() == 0.0) {
                        throw new QfError("E_DOMAIN", "trade quantity is 0", "quantity");
                    }
                    if (closed.contains(e.instrument())) {
                        throw new QfError("E_INPUT", "trade into a closed instrument " + e.instrument(), "events");
                    }
                    trade(book, realized, e.instrument(), e.quantity(), e.price());
                }
                case FIXING -> {
                    Map<LocalDate, Double> m = fixings.computeIfAbsent(e.index(), k -> new TreeMap<>());
                    if (m.containsKey(e.date())) {
                        throw new QfError("E_INPUT", "duplicate fixing " + e.index() + " " + e.date(), "events");
                    }
                    m.put(e.date(), e.value());
                }
                case EXPIRY, DEFAULT -> {
                    Pos p = book.get(e.instrument());
                    if (p == null) {
                        throw new QfError("E_INPUT", "instrument not held " + e.instrument(), "events");
                    }
                    trade(book, realized, e.instrument(), -p.q, e.price());
                    closed.add(e.instrument());
                }
                case ROLL -> {
                    Pos p = book.get(e.from());
                    if (p == null) {
                        throw new QfError("E_INPUT", "instrument not held " + e.from(), "events");
                    }
                    if (closed.contains(e.to())) {
                        throw new QfError("E_INPUT", "roll into a closed instrument " + e.to(), "events");
                    }
                    double q = p.q;
                    trade(book, realized, e.from(), -q, e.fromPrice());
                    closed.add(e.from());
                    trade(book, realized, e.to(), q, e.toPrice());
                }
            }
        }
        List<Position> out = new ArrayList<>();
        book.forEach((k, v) -> out.add(new Position(k, v.q, v.a)));
        double total = 0.0;
        for (double v : realized.values()) {
            total += v;
        }
        List<Fixing> fx = new ArrayList<>();
        fixings.forEach((ix, m) -> m.forEach((d, v) -> fx.add(new Fixing(ix, d, v))));
        return new Lifecycle(out, realized, total, fx);
    }

    private static void trade(TreeMap<String, Pos> book, Map<String, Double> realized, String inst, double dq,
                              double price) {
        Pos p = book.get(inst);
        if (p == null || p.q == 0.0 || Math.signum(p.q) == Math.signum(dq)) {
            if (p == null) {
                p = new Pos();
                book.put(inst, p);
            }
            double q2 = p.q + dq;
            p.a = (p.q * p.a + dq * price) / q2;
            p.q = q2;
            return;
        }
        double c = Math.min(Math.abs(dq), Math.abs(p.q));
        realized.merge(inst, Math.signum(p.q) * c * (price - p.a), Double::sum);
        double q2 = p.q + dq;
        if (Math.abs(dq) == Math.abs(p.q)) {
            book.remove(inst);
        } else if (Math.signum(q2) == Math.signum(p.q)) {
            p.q = q2;
        } else {
            p.q = q2;
            p.a = price;
        }
    }

    // ---- marks ----

    public record Quote(String instrument, LocalDate date, double price) {}

    public record Source(String name, List<Quote> quotes) {}

    public record Mark(String instrument, Double price, String source, String status, Long ageDays, Double ipvDiff,
                       boolean ipvBreach) {}

    public static List<Mark> resolve(LocalDate asOf, List<String> instruments, List<Source> sources, long maxAge,
                                     Map<String, Double> ipv, double threshold) {
        if (maxAge < 0) {
            throw new QfError("E_DOMAIN", "max_age_days must not be negative", "max_age_days");
        }
        Set<String> names = new HashSet<>();
        for (Source s : sources) {
            if (!names.add(s.name())) {
                throw new QfError("E_INPUT", "duplicate source name " + s.name(), "sources");
            }
        }
        for (double v : ipv.values()) {
            if (!(v > 0.0)) {
                throw new QfError("E_DOMAIN", "ipv price must be positive", "ipv");
            }
        }
        List<Mark> out = new ArrayList<>();
        for (String inst : instruments) {
            Double price = null;
            String source = null;
            String status = "MISSING";
            Long age = null;
            for (int k = 0; k < sources.size() && price == null; k++) {
                for (Quote q : sources.get(k).quotes()) {
                    if (q.instrument().equals(inst) && q.date().equals(asOf)) {
                        price = q.price();
                        source = sources.get(k).name();
                        status = k == 0 ? "PRIMARY" : "FALLBACK";
                        age = 0L;
                        break;
                    }
                }
            }
            if (price == null) {
                LocalDate best = null;
                for (Source s : sources) {
                    for (Quote q : s.quotes()) {
                        if (!q.instrument().equals(inst) || !q.date().isBefore(asOf)) {
                            continue;
                        }
                        long gap = ChronoUnit.DAYS.between(q.date(), asOf);
                        if (gap <= maxAge && (best == null || q.date().isAfter(best))) {
                            best = q.date();
                            price = q.price();
                            source = s.name();
                            status = "STALE";
                            age = gap;
                        }
                    }
                }
            }
            Double diff = null;
            boolean breach = false;
            Double ref = ipv.get(inst);
            if (ref != null && price != null) {
                diff = (price - ref) / ref;
                breach = Math.abs(diff) > threshold;
            }
            out.add(new Mark(inst, price, source, status, age, diff, breach));
        }
        return out;
    }

    /** Helper so callers can build an ordered ipv map. */
    public static Map<String, Double> ipvMap(List<String> instruments, double[] prices) {
        Map<String, Double> m = new HashMap<>();
        for (int i = 0; i < prices.length; i++) {
            m.put(instruments.get(i), prices[i]);
        }
        return m;
    }
}
