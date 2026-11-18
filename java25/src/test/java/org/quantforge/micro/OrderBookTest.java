package org.quantforge.micro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;

/** micro.book.rebuild: validation paths, gaps, resyncs, checkpoints, crossed and locked books, event cap. */
class OrderBookTest {
    private static List<?> js(String text) {
        return (List<?>) Json.parse(text).value();
    }

    private static Map<String, Object> run(String msgs, long depth, String cps, boolean emit) {
        return OrderBook.rebuild(js(msgs), depth, 1, 1, cps == null ? null : js(cps), emit);
    }

    private static String code(String msgs, long depth, long pd, long qd, String cps) {
        return assertThrows(QfError.class,
                () -> OrderBook.rebuild(js(msgs), depth, pd, qd, cps == null ? null : js(cps), false)).code();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Long> stats(Map<String, Object> out) {
        return (Map<String, Long>) out.get("stats");
    }

    @Test
    void argumentAndSchemaErrors() {
        String ok = "[]";
        assertEquals("E_DOMAIN", code(ok, 7, 1, 1, null));
        assertEquals("E_DOMAIN", code(ok, 10, -1, 1, null));
        assertEquals("E_DOMAIN", code(ok, 10, 19, 1, null));
        assertEquals("E_DOMAIN", code(ok, 10, 1, -1, null));
        assertEquals("E_DOMAIN", code(ok, 10, 1, 19, null));
        assertEquals("E_SCHEMA", code("[1]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"x\"}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"checksum\":-1}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"checksum\":1.5}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"checksum\":4294967296}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"checksum\":\"1\"}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"t\":5}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"t\":\"nope\"}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"bids\":3}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"bids\":[[\"1\"]]}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"bids\":[3]}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"bids\":[[1,\"1\"]]}]", 10, 1, 1, null));
        assertEquals("E_SCHEMA", code("[{\"type\":\"snapshot\",\"bids\":[[\"1e3\",\"1\"]]}]", 10, 1, 1, null));
        assertEquals("E_DOMAIN", code("[{\"type\":\"snapshot\",\"bids\":[[\"0\",\"1\"]]}]", 10, 1, 1, null));
        assertEquals("E_DOMAIN", code("[{\"type\":\"snapshot\",\"asks\":[[\"1\",\"-1\"]]}]", 10, 1, 1, null));
        assertEquals("E_LIMIT", code("[{\"type\":\"snapshot\",\"asks\":[[\"1.0000000000000000001\",\"1\"]]}]", 10, 1,
                1, null));
        assertEquals("E_LIMIT", code("[{\"type\":\"snapshot\",\"asks\":[[\"1" + "0".repeat(36) + "\",\"1\"]]}]", 10, 1,
                1, null));
        assertEquals("E_SCHEMA", code(ok, 10, 1, 1, "[1]"));
        assertEquals("E_SCHEMA", code(ok, 10, 1, 1, "[{}]"));
    }

    @Test
    void componentAndRange() {
        assertEquals("1230", OrderBook.component("12.3", 2));
        assertEquals("0", OrderBook.component("0.00", 2));
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> OrderBook.component("1.234", 2)).code());
        assertEquals(BigDecimal.ZERO, OrderBook.range(BigDecimal.ZERO, "x", 18));
    }

    @Test
    void snapshotUpdatesGapResyncAndChecksums() {
        String snap = "{\"type\":\"snapshot\",\"bids\":[[\"10.0\",\"1.0\"],[\"9.0\",\"0\"]],\"asks\":[[\"11.0\",\"2.0\"]]}";
        Map<String, Object> first = run("[" + snap + "]", 10, null, true);
        long good = OrderBook.crc32((String) first.get("checksum_string"));
        String msgs = "[{\"type\":\"update\",\"bids\":[[\"1.0\",\"1.0\"]]},"
                + snap.replace("}", ",\"checksum\":" + good + "}")
                + ",{\"type\":\"update\",\"bids\":[[\"9.5\",\"1.0\"],[\"8.0\",\"0\"]],\"asks\":[[\"11.0\",\"0\"]],"
                + "\"checksum\":1},"
                + "{\"type\":\"snapshot\",\"resubscribe\":true,\"bids\":[[\"10.0\",\"1.0\"]],\"asks\":[[\"10.0\",\"1.0\"]]},"
                + "{\"type\":\"update\",\"asks\":[[\"9.0\",\"1.0\"]]},"
                + "{\"type\":\"gap\"}]";
        Map<String, Object> out = run(msgs, 10, null, false);
        Map<String, Long> s = stats(out);
        assertEquals(5L, s.get("messages"));
        assertEquals(2L, s.get("snapshots"));
        assertEquals(3L, s.get("updates"));
        assertEquals(1L, s.get("deletes_of_absent_level"));
        assertEquals(2L, s.get("checksum_checked"));
        assertEquals(1L, s.get("checksum_failed"));
        assertEquals(1L, s.get("resyncs"));
        assertEquals(1L, s.get("locked"));
        assertEquals(1L, s.get("crossed"));
        assertEquals(1L, s.get("gaps"));
        assertFalse(out.containsKey("checksum_string"));
    }

    @Test
    void truncatesToDepth() {
        StringBuilder b = new StringBuilder("[{\"type\":\"snapshot\",\"bids\":[");
        for (int k = 1; k <= 12; k++) {
            b.append(k > 1 ? "," : "").append("[\"").append(k).append(".0\",\"1.0\"]");
        }
        b.append("]}]");
        Map<String, Object> out = run(b.toString(), 10, null, false);
        assertEquals(2L, stats(out).get("truncated_levels"));
        assertEquals(10, ((List<?>) ((Map<?, ?>) out.get("book")).get("bids")).size());
    }

    @Test
    void checkpointsPassAndFail() {
        String msgs = "[{\"type\":\"snapshot\",\"t\":\"2026-01-01T00:00:00Z\",\"bids\":[[\"10.0\",\"1.0\"]],"
                + "\"asks\":[[\"11.0\",\"1.0\"]]},"
                + "{\"type\":\"update\",\"t\":\"2026-01-01T00:00:10\",\"bids\":[[\"10.0\",\"2.0\"]]},"
                + "{\"type\":\"update\"}]";
        String cps = "[{\"t\":\"2026-01-01T00:00:05Z\",\"bids\":[[\"10.0\",\"1.0\"]],\"asks\":[[\"11.0\",\"1.0\"]]},"
                + "{\"t\":\"2026-01-01T00:00:06Z\",\"bids\":[[\"10.0\",\"9.0\"]],\"asks\":[]},"
                + "{\"t\":\"2026-01-01T00:00:07Z\",\"bids\":[[\"10.0\",\"2.0\"],[\"9.0\",\"1.0\"]]},"
                + "{\"t\":\"2026-01-01T00:00:20Z\",\"bids\":[[\"10.0\",\"2.0\"]],\"asks\":[[\"11.0\",\"1.0\"]]}]";
        Map<String, Long> s = stats(run(msgs, 10, cps, false));
        assertEquals(4L, s.get("checkpoint_checked"));
        assertEquals(2L, s.get("checkpoint_failed"));
    }

    @Test
    void eventCapCountsOmitted() {
        List<Object> msgs = new ArrayList<>();
        for (int k = 0; k < OrderBook.MAX_EVENTS + 3; k++) {
            msgs.add(Map.of("type", "gap"));
        }
        Map<String, Object> out = OrderBook.rebuild(msgs, 25, 0, 0, List.of(), false);
        assertEquals(3L, out.get("events_omitted"));
        assertTrue(((List<?>) out.get("events")).size() == OrderBook.MAX_EVENTS);
    }
}
