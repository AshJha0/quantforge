package org.quantforge.micro;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Pattern;
import java.util.zip.CRC32;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;

/**
 * {@code micro.book.rebuild}: market-by-price book rebuild from Kraken-style L2 messages
 * ({@code specifications/09-microstructure/order-book.md}, rulings HR-11 to HR-17, HR-29, HR-41). Prices and
 * quantities are exact decimals kept as the strings received (HR-12). Checksum failures, crossed and locked books are
 * counted and reported, never raised.
 */
public final class OrderBook {
    private OrderBook() {}

    public static final int[] DEPTHS = {10, 25, 100, 500, 1000};
    public static final long MAX_MESSAGES = 50_000_000L;
    public static final int MAX_EVENTS = 10_000;
    private static final Pattern DEC = Pattern.compile("-?[0-9]+(\\.[0-9]+)?");
    private static final String[] STATS = {"messages", "snapshots", "updates", "level_changes",
        "deletes_of_absent_level", "truncated_levels", "checksum_checked", "checksum_failed", "checkpoint_checked",
        "checkpoint_failed", "crossed", "locked", "gaps", "resyncs"};

    private record Level(BigDecimal p, String ptext, BigDecimal q, String qtext) {}

    private record Msg(String kind, List<Level> bids, List<Level> asks, Long cs, boolean resub, Instant t) {}

    private record Checkpoint(Instant t, List<Level> bids, List<Level> asks) {}

    static BigDecimal dec(Object v, String path) {
        if (!(v instanceof String s) || !DEC.matcher(s).matches()) {
            throw new QfError("E_SCHEMA", path + ": not a decimal string", path);
        }
        return new BigDecimal(s);
    }

    private static List<Level> levels(Map<?, ?> m, String key, String path) {
        if (!m.containsKey(key)) {
            return List.of();
        }
        if (!(m.get(key) instanceof List<?> raw)) {
            throw new QfError("E_SCHEMA", path + ": not an array", path);
        }
        List<Level> out = new ArrayList<>();
        for (int k = 0; k < raw.size(); k++) {
            if (!(raw.get(k) instanceof List<?> lv) || lv.size() != 2) {
                throw new QfError("E_SCHEMA", path + "/" + k + ": not a [price, qty] pair", path);
            }
            BigDecimal p = dec(lv.get(0), path + "/" + k + "/0");
            BigDecimal q = dec(lv.get(1), path + "/" + k + "/1");
            if (p.signum() <= 0) {
                throw new QfError("E_DOMAIN", path + "/" + k + ": price must be positive", path);
            }
            if (q.signum() < 0) {
                throw new QfError("E_DOMAIN", path + "/" + k + ": negative quantity", path);
            }
            out.add(new Level(p, (String) lv.get(0), q, (String) lv.get(1)));
        }
        return out;
    }

    /** [KR-CRC]: the value at the pair's precision, decimal point and leading zeros removed. */
    static String component(String text, int decimals) {
        String fixed;
        try {
            fixed = new BigDecimal(text).setScale(decimals, RoundingMode.UNNECESSARY).toPlainString();
        } catch (ArithmeticException e) {
            throw new QfError("E_DOMAIN", text + " has more than " + decimals + " decimals", text);
        }
        String s = fixed.replace(".", "");
        int k = 0;
        while (k < s.length() && s.charAt(k) == '0') {
            k++;
        }
        return k == s.length() ? "0" : s.substring(k);
    }

    public static long crc32(String bookString) {
        CRC32 c = new CRC32();
        c.update(bookString.getBytes(StandardCharsets.US_ASCII));
        return c.getValue();
    }

    private static Instant instant(Object v, String path) {
        if (!(v instanceof String s)) {
            throw new QfError("E_SCHEMA", path + ": not a timestamp", path);
        }
        try {
            return OffsetDateTime.parse(s).toInstant();
        } catch (DateTimeParseException e) {
            try {
                return LocalDateTime.parse(s).toInstant(ZoneOffset.UTC);
            } catch (DateTimeParseException e2) {
                throw new QfError("E_SCHEMA", path + ": not a timestamp", path);
            }
        }
    }

    /** One side keyed by exact price; the value holds the latest price text and quantity text. */
    private static final class Book {
        final int depth;
        final TreeMap<BigDecimal, String[]> bids = new TreeMap<>(Comparator.reverseOrder());
        final TreeMap<BigDecimal, String[]> asks = new TreeMap<>();

        Book(int depth) {
            this.depth = depth;
        }

        TreeMap<BigDecimal, String[]> side(boolean bid) {
            return bid ? bids : asks;
        }

        int truncate() {
            int dropped = 0;
            for (boolean bid : new boolean[] {true, false}) {
                TreeMap<BigDecimal, String[]> d = side(bid);
                while (d.size() > depth) {
                    d.pollLastEntry();
                    dropped++;
                }
            }
            return dropped;
        }

        List<List<String>> ordered(boolean bid) {
            List<List<String>> out = new ArrayList<>();
            for (String[] v : side(bid).values()) {
                out.add(List.of(v[0], v[1]));
            }
            return out;
        }

        String checksumString(int pdec, int qdec) {
            StringBuilder b = new StringBuilder();
            for (boolean bid : new boolean[] {false, true}) {
                int n = 0;
                for (String[] v : side(bid).values()) {
                    if (n++ == 10) {
                        break;
                    }
                    b.append(component(v[0], pdec)).append(component(v[1], qdec));
                }
            }
            return b.toString();
        }
    }

    public static Map<String, Object> rebuild(List<?> messages, long depth, long priceDecimals, long qtyDecimals,
            List<?> checkpoints, boolean emitChecksumString) {
        boolean okDepth = false;
        for (int d : DEPTHS) {
            okDepth |= d == depth;
        }
        if (!okDepth) {
            throw new QfError("E_DOMAIN", "depth must be one of 10, 25, 100, 500, 1000", "depth");
        }
        if (priceDecimals < 0 || priceDecimals > 18 || qtyDecimals < 0 || qtyDecimals > 18) {
            throw new QfError("E_DOMAIN", "decimals out of range", "price_decimals");
        }
        if (messages.size() > MAX_MESSAGES) {
            throw new QfError("E_LIMIT", "more than 50,000,000 messages", "messages");
        }
        int pdec = (int) priceDecimals;
        int qdec = (int) qtyDecimals;
        List<Msg> parsed = new ArrayList<>();
        for (int i = 0; i < messages.size(); i++) {
            Object type = messages.get(i) instanceof Map<?, ?> mm ? mm.get("type") : null;
            if (!("snapshot".equals(type) || "update".equals(type) || "gap".equals(type))) {
                throw new QfError("E_SCHEMA", "messages/" + i + ": not a message", "messages");
            }
            Map<?, ?> m = (Map<?, ?>) messages.get(i);
            if ("gap".equals(type)) {
                parsed.add(new Msg("gap", null, null, null, false, null));
                continue;
            }
            Object csRaw = m.get("checksum");
            Long cs = null;
            if (csRaw != null) {
                if (!(csRaw instanceof Json.Number n) || !n.isIntegerForm() || n.value() < 0 || n.value() >= 0x1p32) {
                    throw new QfError("E_SCHEMA", "messages/" + i + "/checksum: not a u32", "messages");
                }
                cs = (long) n.value();
            }
            Instant t = m.get("t") != null ? instant(m.get("t"), "messages/" + i + "/t") : null;
            parsed.add(new Msg((String) type, levels(m, "bids", "messages/" + i + "/bids"),
                    levels(m, "asks", "messages/" + i + "/asks"), cs, Boolean.TRUE.equals(m.get("resubscribe")), t));
        }
        List<Checkpoint> cps = new ArrayList<>();
        List<?> cpIn = checkpoints == null ? List.of() : checkpoints;
        for (int k = 0; k < cpIn.size(); k++) {
            if (!(cpIn.get(k) instanceof Map<?, ?> c)) {
                throw new QfError("E_SCHEMA", "checkpoints/" + k + ": not an object", "checkpoints");
            }
            cps.add(new Checkpoint(instant(c.get("t"), "checkpoints/" + k + "/t"),
                    levels(c, "bids", "checkpoints/" + k + "/bids"), levels(c, "asks", "checkpoints/" + k + "/asks")));
        }
        return new Run(depth, pdec, qdec, cps).go(parsed, emitChecksumString);
    }

    private static final class Run {
        final int depth;
        final int pdec;
        final int qdec;
        final List<Checkpoint> cps;
        final Map<String, Long> stats = new LinkedHashMap<>();
        final List<Object> events = new ArrayList<>();
        long omitted;
        Book book;
        int cpNext;

        Run(long depth, int pdec, int qdec, List<Checkpoint> cps) {
            this.depth = (int) depth;
            this.pdec = pdec;
            this.qdec = qdec;
            this.cps = cps;
            for (String s : STATS) {
                stats.put(s, 0L);
            }
            book = new Book(this.depth);
        }

        void inc(String k) {
            stats.merge(k, 1L, Long::sum);
        }

        void event(int i, String kind) {
            if (events.size() < MAX_EVENTS) {
                Map<String, Object> e = new LinkedHashMap<>();
                e.put("i", (long) i);
                e.put("kind", kind);
                events.add(e);
            } else {
                omitted++;
            }
        }

        void checkpoint(int i, Instant upto) {
            while (cpNext < cps.size() && (upto == null || cps.get(cpNext).t().isBefore(upto))) {
                Checkpoint cp = cps.get(cpNext++);
                inc("checkpoint_checked");
                boolean ok = true;
                for (boolean bid : new boolean[] {true, false}) {
                    List<Level> lv = bid ? cp.bids() : cp.asks();
                    List<Map.Entry<BigDecimal, String[]>> ours = new ArrayList<>(book.side(bid).entrySet());
                    ours = ours.subList(0, Math.min(ours.size(), lv.size()));
                    List<Level> want = new ArrayList<>(lv);
                    Comparator<Level> c = Comparator.comparing(Level::p).thenComparing(Level::q);
                    want.sort(bid ? c.reversed() : c);
                    if (ours.size() != want.size()) {
                        ok = false;
                        continue;
                    }
                    for (int k = 0; k < ours.size(); k++) {
                        if (ours.get(k).getKey().compareTo(want.get(k).p()) != 0
                                || new BigDecimal(ours.get(k).getValue()[1]).compareTo(want.get(k).q()) != 0) {
                            ok = false;
                        }
                    }
                }
                if (!ok) {
                    inc("checkpoint_failed");
                    event(i, "CHECKPOINT_FAIL");
                }
            }
        }

        Map<String, Object> go(List<Msg> parsed, boolean emit) {
            boolean live = false;
            boolean pendingResync = false;
            for (int i = 0; i < parsed.size(); i++) {
                Msg m = parsed.get(i);
                if (m.kind().equals("gap")) {
                    inc("gaps");
                    book = new Book(depth);
                    live = false;
                    event(i, "GAP");
                    continue;
                }
                if (!cps.isEmpty() && m.t() != null) {
                    checkpoint(i - 1, m.t());
                }
                inc("messages");
                if (m.kind().equals("snapshot")) {
                    inc("snapshots");
                    if (m.resub() && pendingResync) {
                        inc("resyncs");
                    }
                    pendingResync = false;
                    book = new Book(depth);
                    for (boolean bid : new boolean[] {true, false}) {
                        for (Level l : bid ? m.bids() : m.asks()) {
                            if (l.q().signum() != 0) {
                                book.side(bid).put(l.p(), new String[] {l.ptext(), l.qtext()});
                            }
                        }
                    }
                    live = true;
                } else {
                    inc("updates");
                    if (!live) {
                        event(i, "UPDATE_BEFORE_SNAPSHOT");
                        continue;
                    }
                    for (boolean bid : new boolean[] {true, false}) {
                        TreeMap<BigDecimal, String[]> d = book.side(bid);
                        for (Level l : bid ? m.bids() : m.asks()) {
                            inc("level_changes");
                            if (l.q().signum() == 0) {
                                if (d.remove(l.p()) == null) {
                                    inc("deletes_of_absent_level");
                                }
                            } else {
                                d.put(l.p(), new String[] {l.ptext(), l.qtext()});
                            }
                        }
                    }
                }
                stats.merge("truncated_levels", (long) book.truncate(), Long::sum);
                if (m.cs() != null) {
                    inc("checksum_checked");
                    if (crc32(book.checksumString(pdec, qdec)) != m.cs()) {
                        inc("checksum_failed");
                        pendingResync = true;
                        event(i, "CHECKSUM_FAIL");
                    }
                }
                if (!book.bids.isEmpty() && !book.asks.isEmpty()) {
                    int c = book.bids.firstKey().compareTo(book.asks.firstKey());
                    if (c > 0) {
                        inc("crossed");
                        event(i, "CROSSED");
                    } else if (c == 0) {
                        inc("locked");
                        event(i, "LOCKED");
                    }
                }
            }
            if (!cps.isEmpty()) {
                checkpoint(parsed.size() - 1, null);
            }
            String fin = book.checksumString(pdec, qdec);
            Map<String, Object> b = new LinkedHashMap<>();
            b.put("bids", book.ordered(true));
            b.put("asks", book.ordered(false));
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("book", b);
            out.put("stats", stats);
            out.put("events", events);
            out.put("crc32", crc32(fin));
            if (omitted > 0) {
                out.put("events_omitted", omitted);
            }
            if (emit) {
                out.put("checksum_string", fin);
            }
            return out;
        }
    }
}
