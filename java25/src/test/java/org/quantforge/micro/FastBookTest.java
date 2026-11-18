package org.quantforge.micro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigInteger;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.quantforge.core.Rng;

/**
 * H-9 low-latency book ({@code low-latency-book.md}, "Golden plan"): every ob_h golden row through {@link FastBook}
 * (book, crc32, stats and events equal; error rows rejected by the decoder with the golden's code; ob_h-0016 is
 * outside the int64 fixed-point range and is E_LIMIT, the stated scope limit, HR-58); and the property test: 1,000
 * seeded streams of 10,000 messages, top(100), qtyAt and the cached best equal a TreeMap transcription of the
 * normative algorithm after every message, and the final book, crc32, stats and events equal
 * {@link OrderBook#rebuild}.
 */
class FastBookTest {
    static final class DecodeError extends RuntimeException {
        final String code;

        DecodeError(String code) {
            super(code);
            this.code = code;
        }
    }

    static long toFixed(Object v, int dec, boolean isPrice) {
        if (!(v instanceof String s)) {
            throw new DecodeError("E_SCHEMA");
        }
        if (!s.matches("-?[0-9]+(\\.[0-9]+)?")) {
            throw new DecodeError("E_SCHEMA");
        }
        boolean neg = s.startsWith("-");
        String body = neg ? s.substring(1) : s;
        int dot = body.indexOf('.');
        String ip = dot < 0 ? body : body.substring(0, dot);
        String fp = dot < 0 ? "" : body.substring(dot + 1);
        if (ip.length() + fp.length() > 36 || fp.length() > 18) {
            throw new DecodeError("E_LIMIT");
        }
        boolean zero = (ip + fp).chars().allMatch(c -> c == '0');
        if (neg && !zero || isPrice && zero) {
            throw new DecodeError("E_DOMAIN");
        }
        if (fp.length() > dec && !fp.substring(dec).chars().allMatch(c -> c == '0')) {
            throw new DecodeError("E_DOMAIN");
        }
        String d = ip + (fp + "0".repeat(18)).substring(0, dec);
        BigInteger b = new BigInteger(d);
        if (b.bitLength() > 63) {
            throw new DecodeError("E_LIMIT");  // HR-58: above the fast book's int64 range
        }
        return b.longValue();
    }

    static FastBook.Stream decode(Map<?, ?> in) {
        long depth = (long) ((Json.Number) in.get("depth")).value();
        if (depth != 10 && depth != 25 && depth != 100 && depth != 500 && depth != 1000) {
            throw new DecodeError("E_DOMAIN");
        }
        int pd = (int) ((Json.Number) in.get("price_decimals")).value();
        int qd = (int) ((Json.Number) in.get("qty_decimals")).value();
        List<?> msgs = (List<?>) in.get("messages");
        List<long[]> lv = new ArrayList<>();
        FastBook.Stream st = new FastBook.Stream(msgs.size(), 0);
        for (int i = 0; i < msgs.size(); i++) {
            Map<?, ?> m = (Map<?, ?>) msgs.get(i);
            Object type = m.get("type");
            st.first[i] = lv.size();
            if ("gap".equals(type)) {
                st.type[i] = FastBook.GAP;
                continue;
            }
            if ("snapshot".equals(type)) {
                st.type[i] = FastBook.SNAPSHOT;
            } else if ("update".equals(type)) {
                st.type[i] = FastBook.UPDATE;
            } else {
                throw new DecodeError("E_SCHEMA");
            }
            for (String side : new String[] {"bids", "asks"}) {
                List<?> arr = (List<?>) m.get(side);
                for (Object l : arr) {
                    List<?> pair = (List<?>) l;
                    lv.add(new long[] {toFixed(pair.get(0), pd, true), toFixed(pair.get(1), qd, false)});
                }
                if (side.equals("bids")) {
                    st.nBids[i] = (short) arr.size();
                } else {
                    st.nAsks[i] = (short) arr.size();
                }
            }
            if (m.get("checksum") instanceof Json.Number n) {
                st.flags[i] |= FastBook.FLAG_CHECKSUM;
                st.checksum[i] = (long) n.value();
            }
            if (Boolean.TRUE.equals(m.get("resubscribe"))) {
                st.flags[i] |= FastBook.FLAG_RESUBSCRIBE;
            }
        }
        st.px = lv.stream().mapToLong(a -> a[0]).toArray();
        st.qty = lv.stream().mapToLong(a -> a[1]).toArray();
        return st;
    }

    static String fixedText(long v, int dec) {
        String d = Long.toString(v);
        if (dec == 0) {
            return d;
        }
        if (d.length() <= dec) {
            d = "0".repeat(dec + 1 - d.length()) + d;
        }
        return d.substring(0, d.length() - dec) + "." + d.substring(d.length() - dec);
    }

    static String summaryOfBook(FastBook b, int pd, int qd) {
        StringBuilder o = new StringBuilder();
        long[] px = new long[b.depth()];
        long[] q = new long[b.depth()];
        for (boolean bid : new boolean[] {false, true}) {
            int n = b.top(bid, b.depth(), px, q);
            o.append(bid ? " bids[" : "asks[");
            for (int k = 0; k < n; k++) {
                o.append(k > 0 ? "," : "").append(fixedText(px[k], pd)).append(':').append(fixedText(q[k], qd));
            }
            o.append(']');
        }
        o.append(" crc ").append(b.checksum()).append(" stats");
        TreeMap<String, Long> st = new TreeMap<>(Map.ofEntries(Map.entry("checkpoint_checked", 0L),
                Map.entry("checkpoint_failed", 0L), Map.entry("checksum_checked", b.checksumChecked),
                Map.entry("checksum_failed", b.checksumFailed), Map.entry("crossed", b.crossed),
                Map.entry("deletes_of_absent_level", b.deletesOfAbsentLevel), Map.entry("gaps", b.gaps),
                Map.entry("level_changes", b.levelChanges), Map.entry("locked", b.locked),
                Map.entry("messages", b.messages), Map.entry("resyncs", b.resyncs), Map.entry("snapshots", b.snapshots),
                Map.entry("truncated_levels", b.truncatedLevels), Map.entry("updates", b.updates)));
        st.forEach((k, v) -> o.append(' ').append(k).append('=').append(v));
        o.append(" events");
        for (int k = 0; k < b.eventCount(); k++) {
            o.append(k > 0 ? "," : " ").append(b.eventIndex(k)).append(':').append(b.eventName(k));
        }
        return o.toString();
    }

    static long num(Object v) {
        return v instanceof Json.Number n ? (long) n.value() : ((Number) v).longValue();
    }

    static String summaryOfOutputs(Map<?, ?> out) {
        StringBuilder o = new StringBuilder();
        Map<?, ?> book = (Map<?, ?>) out.get("book");
        for (String side : new String[] {"asks", "bids"}) {
            o.append(side.equals("bids") ? " bids[" : "asks[");
            List<?> l = (List<?>) book.get(side);
            for (int k = 0; k < l.size(); k++) {
                List<?> p = (List<?>) l.get(k);
                o.append(k > 0 ? "," : "").append(p.get(0)).append(':').append(p.get(1));
            }
            o.append(']');
        }
        o.append(" crc ").append(num(out.get("crc32"))).append(" stats");
        TreeMap<String, Long> st = new TreeMap<>();
        ((Map<?, ?>) out.get("stats")).forEach((k, v) -> st.put((String) k, num(v)));
        st.forEach((k, v) -> o.append(' ').append(k).append('=').append(v));
        o.append(" events");
        List<?> ev = (List<?>) out.get("events");
        for (int k = 0; k < ev.size(); k++) {
            Map<?, ?> e = (Map<?, ?>) ev.get(k);
            o.append(k > 0 ? "," : " ").append(num(e.get("i"))).append(':').append(e.get("kind"));
        }
        return o.toString();
    }

    static FastBook run(FastBook.Stream st, int depth) {
        FastBook b = new FastBook(depth);
        for (int i = 0; i < st.messages; i++) {
            b.apply(st, i);
        }
        return b;
    }

    @Test
    void obHGoldens() throws Exception {
        String text = Files.readString(Path.of("..", "datasets", "golden", "stage_h", "ob_h.json"));
        Map<?, ?> golden = (Map<?, ?>) Json.parse(text).value();
        int ok = 0;
        int rejected = 0;
        for (Object c : (List<?>) golden.get("cases")) {
            Map<?, ?> cs = (Map<?, ?>) c;
            String id = (String) cs.get("case_id");
            Map<?, ?> in = (Map<?, ?>) cs.get("inputs");
            Map<?, ?> exp = (Map<?, ?>) cs.get("expected");
            String code = null;
            FastBook.Stream st = null;
            try {
                st = decode(in);
            } catch (DecodeError e) {
                code = e.code;
            }
            if (id.equals("ob_h-0016")) {
                assertEquals("E_LIMIT", code, id + ": stated int64 range limit (HR-58)");
                continue;
            }
            if (!"ok".equals(exp.get("status"))) {
                assertEquals(exp.get("error_code"), code, id);
                rejected++;
                continue;
            }
            int depth = (int) num(in.get("depth"));
            assertEquals(summaryOfOutputs((Map<?, ?>) exp.get("outputs")),
                    summaryOfBook(run(st, depth), (int) num(in.get("price_decimals")), (int) num(in.get("qty_decimals"))),
                    id);
            ok++;
        }
        assertEquals(9, ok);
        assertEquals(7, rejected);
    }

    /** The C++ test's generator, draw for draw. */
    static FastBook.Stream randomStream(long seed, int depth, int n) {
        Rng r = Rng.seeded(seed, 0);
        List<long[]> lv = new ArrayList<>();
        FastBook.Stream st = new FastBook.Stream(n, 0);
        long mid = 1000;
        long span = depth + 20;
        for (int i = 0; i < n; i++) {
            st.first[i] = lv.size();
            long roll = Long.remainderUnsigned(r.nextLong(), 1000);
            int type = roll < 3 ? FastBook.GAP : roll < 15 || i == 1 ? FastBook.SNAPSHOT
                    : roll < 40 ? FastBook.TRADE : FastBook.UPDATE;
            st.type[i] = (byte) type;
            if (type == FastBook.TRADE) {
                lv.add(new long[] {mid + Long.remainderUnsigned(r.nextLong(), 10), 1 + Long.remainderUnsigned(r.nextLong(), 100)});
                st.nBids[i] = 1;
            } else if (type != FastBook.GAP) {
                boolean snap = type == FastBook.SNAPSHOT;
                for (int side = 0; side < 2; side++) {
                    long l = snap ? Long.remainderUnsigned(r.nextLong(), depth + 15)
                            : Long.remainderUnsigned(r.nextLong(), 10) < 7 ? Long.remainderUnsigned(r.nextLong(), 2)
                            : Long.remainderUnsigned(r.nextLong(), 6);
                    for (int k = 0; k < l; k++) {
                        long d = Long.remainderUnsigned(r.nextLong(), span);
                        long px = side == 0 ? mid + 3 - d : mid - 3 + d;
                        boolean zero = snap ? Long.remainderUnsigned(r.nextLong(), 20) == 0
                                : Long.remainderUnsigned(r.nextLong(), 10) < 3;
                        lv.add(new long[] {px, zero ? 0 : 1 + Long.remainderUnsigned(r.nextLong(), 1_000_000)});
                    }
                    if (side == 0) {
                        st.nBids[i] = (short) l;
                    } else {
                        st.nAsks[i] = (short) l;
                    }
                }
                if (Long.remainderUnsigned(r.nextLong(), 20) == 0) {
                    st.flags[i] |= FastBook.FLAG_CHECKSUM;
                    st.checksum[i] = r.nextLong() & 0xFFFFFFFFL;
                }
                if (snap && Long.remainderUnsigned(r.nextLong(), 3) == 0) {
                    st.flags[i] |= FastBook.FLAG_RESUBSCRIBE;
                }
            }
        }
        st.px = lv.stream().mapToLong(a -> a[0]).toArray();
        st.qty = lv.stream().mapToLong(a -> a[1]).toArray();
        return st;
    }

    static String toJson(FastBook.Stream st) {
        StringBuilder o = new StringBuilder("[");
        boolean first = true;
        for (int i = 0; i < st.messages; i++) {
            if (st.type[i] == FastBook.TRADE) {
                continue;
            }
            o.append(first ? "" : ",");
            first = false;
            if (st.type[i] == FastBook.GAP) {
                o.append("{\"type\":\"gap\"}");
                continue;
            }
            o.append("{\"type\":\"").append(st.type[i] == FastBook.SNAPSHOT ? "snapshot" : "update")
                    .append("\",\"t\":\"2026-01-01T00:00:00Z\",\"checksum\":")
                    .append((st.flags[i] & FastBook.FLAG_CHECKSUM) != 0 ? Long.toString(st.checksum[i]) : "null");
            if ((st.flags[i] & FastBook.FLAG_RESUBSCRIBE) != 0) {
                o.append(",\"resubscribe\":true");
            }
            for (int side = 0; side < 2; side++) {
                o.append(side == 0 ? ",\"bids\":[" : ",\"asks\":[");
                int base = st.first[i] + (side == 0 ? 0 : st.nBids[i]);
                int n = side == 0 ? st.nBids[i] : st.nAsks[i];
                for (int k = 0; k < n; k++) {
                    o.append(k > 0 ? "," : "").append("[\"").append(fixedText(st.px[base + k], 1)).append("\",\"")
                            .append(fixedText(st.qty[base + k], 8)).append("\"]");
                }
                o.append(']');
            }
            o.append('}');
        }
        return o.append(']').toString();
    }

    @Test
    void property1000Streams() {
        int[] depths = {10, 25, 100};
        long[] px = new long[100];
        long[] q = new long[100];
        for (int s = 0; s < 1000; s++) {
            int depth = depths[s % 3];
            FastBook.Stream st = randomStream(20261117L + s, depth, 10_000);
            FastBook b = new FastBook(depth);
            TreeMap<Long, Long> bids = new TreeMap<>();
            TreeMap<Long, Long> asks = new TreeMap<>();
            boolean live = false;
            for (int i = 0; i < st.messages; i++) {
                b.apply(st, i);
                int t = st.type[i];
                if (t == FastBook.GAP) {
                    bids.clear();
                    asks.clear();
                    live = false;
                } else if (t != FastBook.TRADE && (t == FastBook.SNAPSHOT || live)) {
                    boolean snap = t == FastBook.SNAPSHOT;
                    if (snap) {
                        bids.clear();
                        asks.clear();
                        live = true;
                    }
                    int f = st.first[i];
                    for (int k = f; k < f + st.nBids[i] + st.nAsks[i]; k++) {
                        TreeMap<Long, Long> side = k < f + st.nBids[i] ? bids : asks;
                        if (st.qty[k] != 0) {
                            side.put(st.px[k], st.qty[k]);
                        } else if (!snap) {
                            side.remove(st.px[k]);
                        }
                    }
                    while (bids.size() > depth) {
                        bids.pollFirstEntry();
                    }
                    while (asks.size() > depth) {
                        asks.pollLastEntry();
                    }
                }
                for (boolean bid : new boolean[] {true, false}) {
                    var want = new ArrayList<>((bid ? bids.descendingMap() : asks).entrySet());
                    int n = b.top(bid, 100, px, q);
                    assertEquals(want.size(), n, "stream " + s + " message " + i);
                    for (int k = 0; k < n; k++) {
                        if (px[k] != want.get(k).getKey() || q[k] != want.get(k).getValue()
                                || b.qtyAt(bid, px[k]) != q[k]) {
                            throw new AssertionError("stream " + s + " diverges at message " + i);
                        }
                    }
                    boolean has = bid ? b.hasBestBid() : b.hasBestAsk();
                    assertEquals(n > 0, has);
                    if (n > 0) {
                        assertEquals(px[0], bid ? b.bestBidPx() : b.bestAskPx());
                    }
                }
                assertEquals(0, b.qtyAt(true, 1004 + i % 7));
                assertEquals(0, b.qtyAt(false, 996 - i % 7));
            }
            List<?> msgs = (List<?>) Json.parse(toJson(st)).value();
            Map<String, Object> out = OrderBook.rebuild(msgs, depth, 1, 8, null, false);
            assertEquals(summaryOfOutputs(out), summaryOfBook(b, 1, 8), "stream " + s);
        }
    }

    @Test
    void sharedSlotsAndLimitCases() {
        FastBook.Stream st = new FastBook.Stream(3, 6);
        long[][] lv = {{2148, 3}, {1124, 2}, {101, 4}, {100, 1}, {2148, 0}, {1124, 9}};
        for (int k = 0; k < 6; k++) {
            st.px[k] = lv[k][0];
            st.qty[k] = lv[k][1];
        }
        st.type[0] = FastBook.SNAPSHOT;
        st.nBids[0] = 4;
        st.type[1] = FastBook.UPDATE;
        st.nBids[1] = 2;
        st.first[1] = 4;
        st.type[2] = FastBook.GAP;
        FastBook b = new FastBook(10);
        b.apply(st, 0);
        assertEquals(1, b.qtyAt(true, 100));
        assertEquals(2, b.qtyAt(true, 1124));
        assertEquals(3, b.qtyAt(true, 2148));
        assertEquals(0, b.qtyAt(true, 3172));
        b.apply(st, 1);
        assertEquals(0, b.qtyAt(true, 2148));
        assertEquals(9, b.qtyAt(true, 1124));
        assertEquals(1, b.qtyAt(true, 100));
        assertTrue(b.indexFallbacks() > 0);
        assertEquals(1124, b.bestBidPx());
        b.apply(st, 2);
        assertEquals(false, b.hasBestBid());
        assertEquals(0, b.qtyAt(true, 100));

        FastBook.Stream wide = new FastBook.Stream(1, 400);
        for (int k = 0; k < 400; k++) {
            wide.px[k] = 1000 - k;
            wide.qty[k] = 1;
        }
        wide.nBids[0] = 400;
        FastBook w = new FastBook(10);
        w.apply(wide, 0);
        assertTrue(w.grows() >= 1);
        assertEquals(1000, w.bestBidPx());
        assertEquals(390, w.truncatedLevels);
    }
}
