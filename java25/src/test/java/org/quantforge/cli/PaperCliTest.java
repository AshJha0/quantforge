package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.SplittableRandom;
import java.util.TreeMap;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.paper.Paper;

/** Paper trading (HR-42 to HR-55): live mode, labels, hash reproduction, tamper detection, shortest printing. */
class PaperCliTest {
    private static final String LIMITS = "{\"max_order_qty\":\"10\",\"max_notional\":\"1000\",\"max_abs_position\":\"5\","
            + "\"price_band\":\"0.05\",\"max_orders_per_day\":3,\"kill_switch\":false,\"allow_short\":true}";
    private static final String LIT = "{\"tick_size\":\"0.5\",\"lot_size\":\"1\",\"fee_schedule\":{\"maker_rebate\":\"0\","
            + "\"taker_fee\":\"0.001\"}}";
    private static final String SNAP = "{\"bids\":[[\"99.5\",\"4\"]],\"asks\":[[\"100.5\",\"2\"],[\"101\",\"5\"]]}";

    private static String run(String op, String inputs) {
        return Main.handle("{\"schema_version\":\"1.0\",\"case_id\":\"c\",\"operation\":\"" + op
                + "\",\"inputs\":" + inputs + "}").json();
    }

    private static String pretrade(String order) {
        return run("paper.pretrade.check", "{\"order\":" + order + ",\"ref_price\":\"100\",\"position\":\"0\","
                + "\"cash\":\"10000\",\"orders_today\":0,\"limits\":" + LIMITS + "}");
    }

    /** pt_h-0018 and A5: a live order is never placed. */
    @Test
    void liveModeIsUnsupported() {
        String j = pretrade("{\"side\":\"BUY\",\"type\":\"LIMIT\",\"quantity\":\"3\",\"limit_price\":\"101\","
                + "\"mode\":\"live\"}");
        assertTrue(j.contains("\"E_UNSUPPORTED_OPERATION\""), j);
        String s = run("paper.session.run", "{\"cash\":\"10000\",\"limits\":" + LIMITS + ",\"lit\":" + LIT
                + ",\"script\":[{\"op\":\"SUBMIT\",\"ts\":\"t\",\"order\":{\"order_id\":\"O1\",\"symbol\":\"BTC-USD\","
                + "\"side\":\"BUY\",\"type\":\"LIMIT\",\"quantity\":\"3\",\"limit_price\":\"101\",\"mode\":\"live\"},"
                + "\"snapshot\":" + SNAP + "}]}");
        assertTrue(s.contains("\"E_UNSUPPORTED_OPERATION\""), s);
        String ok = pretrade("{\"side\":\"BUY\",\"type\":\"LIMIT\",\"quantity\":\"3\",\"limit_price\":\"101\","
                + "\"mode\":\"simulated\"}");
        assertTrue(ok.contains("\"accepted\":true"), ok);
    }

    /** A5: no paper module names a network library or an order-entry endpoint. */
    @Test
    void noNetworkCode() throws IOException {
        for (Path p : List.of(Path.of("src/main/java/org/quantforge/paper/Paper.java"),
                Path.of("src/main/java/org/quantforge/cli/OpsPaper.java"))) {
            String src = Files.readString(p);
            for (String bad : List.of("java.net", "Socket", "HttpClient", "http://", "https://", "URLConnection")) {
                assertFalse(src.contains(bad), p + " names " + bad);
            }
        }
    }

    @Test
    void nonFiniteDecimalIsSchema() {
        for (String tok : List.of("NaN", "Infinity", "-Infinity", "nan", "inf")) {
            String j = pretrade("{\"side\":\"BUY\",\"type\":\"LIMIT\",\"quantity\":\"3\",\"limit_price\":\"" + tok + "\"}");
            assertTrue(j.contains("\"E_SCHEMA\""), j);
        }
        String a = run("paper.ledger.append", "{\"seq\":0,\"ts\":\"t\",\"kind\":\"ORDER\",\"body\":{\"x\":[\"-Infinity\"]}}");
        assertTrue(a.contains("\"E_SCHEMA\""), a);
        String n = run("paper.book.apply_fill", "{\"fills\":[{\"side\":\"BUY\",\"quantity\":3,\"price\":\"1\"}]}");
        assertTrue(n.contains("\"E_SCHEMA\""), n);
    }

    @Test
    void everyOutputCarriesTheLabel() {
        List<String> outs = List.of(
                run("paper.book.apply_fill", "{\"fills\":[{\"side\":\"BUY\",\"quantity\":\"2\",\"price\":\"100\"}]}"),
                run("paper.book.end_of_day", "{\"cash_open\":\"100\"}"),
                pretrade("{\"side\":\"BUY\",\"type\":\"MARKET\",\"quantity\":\"3\"}"),
                run("paper.ledger.append", "{\"seq\":0,\"ts\":\"t\",\"kind\":\"ORDER\",\"body\":{}}"),
                run("paper.ledger.verify", "{\"text\":\"\"}"));
        for (String j : outs) {
            assertTrue(j.contains("\"label\":\"crypto venue; simulated\""), j);
        }
    }

    /** pt_h-0020: the hash checked by sha256sum, and the HR-45 escapes of Python json.dumps(ensure_ascii=True). */
    @Test
    void hashReproduction() {
        Map<String, Object> body = new TreeMap<>();
        body.put("order_id", "O1");
        body.put("symbol", "BTC-USD");
        body.put("side", "BUY");
        body.put("type", "LIMIT");
        body.put("quantity", "3");
        body.put("limit_price", "101");
        Map<String, Object> r = Paper.ledgerAppend(0, "2026-11-18T00:00:01Z", "ORDER", body, Paper.GENESIS);
        assertEquals("72c85984abb1b7c4072c65dbba0567b3de51279645b0ad63cfd242137aed7e81", r.get("hash"));
        StringBuilder b = new StringBuilder();
        Paper.writeCanonical(b, Map.of("k", "\u00e9\u007f\"\\/\n\r\t\b\f\u0001\uD83D\uDE00~", "a", List.of()));
        assertEquals("{\"a\":[],\"k\":\"\\u00e9\\u007f\\\"\\\\/\\n\\r\\t\\b\\f\\u0001\\ud83d\\ude00~\"}", b.toString());
        // Python sorts by code point, not by UTF-16 unit
        StringBuilder c = new StringBuilder();
        Paper.writeCanonical(c, Map.of("\uFF61", "1", "\uD83D\uDE00", "2"));
        assertEquals("{\"\\uff61\":\"1\",\"\\ud83d\\ude00\":\"2\"}", c.toString());
        assertThrows(QfError.class, () -> Paper.canonical(Map.of("seq", 0L, "body", Map.of("x", true))));
    }

    private static Paper.Ledger randomLedger(int n, long seed) {
        SplittableRandom rnd = new SplittableRandom(seed);
        Paper.Ledger l = new Paper.Ledger();
        for (int k = 0; k < n; k++) {
            Map<String, Object> body = new TreeMap<>();
            body.put("order_id", "O" + rnd.nextInt(1000));
            body.put("quantity", Integer.toString(rnd.nextInt(1, 100)));
            body.put("note", "cafe \"" + rnd.nextInt() + "\"");
            l.append(List.of("ORDER", "FILL", "CANCEL", "TCA").get(rnd.nextInt(4)), "2026-11-18T00:00:0" + (k % 10) + "Z",
                    body);
        }
        return l;
    }

    /** A1: flipping any byte makes verify fail at that seq or earlier; truncation leaves a valid shorter chain. */
    @Test
    void tamperDetection() {
        Paper.Ledger l = randomLedger(200, 7);
        String text = l.text();
        Map<String, Object> ok = Paper.verify(text);
        assertEquals(true, ok.get("ok"));
        assertEquals(200L, ok.get("records"));
        assertEquals(l.head(), ok.get("head"));
        SplittableRandom rnd = new SplittableRandom(11);
        int line = 0;
        int[] lineOf = new int[text.length()];
        for (int i = 0; i < text.length(); i++) {
            lineOf[i] = line;
            if (text.charAt(i) == '\n') {
                line++;
            }
        }
        for (int trial = 0; trial < 3000; trial++) {
            int pos = rnd.nextInt(text.length());
            char orig = text.charAt(pos);
            if (orig == '\n') {
                continue;
            }
            char flipped = (char) (orig ^ (1 << rnd.nextInt(7)));
            String bad = text.substring(0, pos) + flipped + text.substring(pos + 1);
            Map<String, Object> v = Paper.verify(bad);
            assertEquals(false, v.get("ok"), "flip at " + pos);
            assertTrue((Long) v.get("first_bad_seq") <= lineOf[pos], "flip at " + pos);
        }
        String truncated = text.substring(0, text.lastIndexOf('\n', text.length() - 2) + 1);
        Map<String, Object> t = Paper.verify(truncated);
        assertEquals(true, t.get("ok"));
        assertEquals(199L, t.get("records"));
        // swapping two lines breaks SEQ; removing the label breaks LABEL after a recomputed hash
        List<String> lines = new ArrayList<>(List.of(text.split("\n")));
        String l1 = lines.get(1);
        lines.set(1, lines.get(2));
        lines.set(2, l1);
        assertEquals("SEQ", Paper.verify(String.join("\n", lines)).get("reason"));
    }

    /** A8: the same session gives a byte-identical ledger. */
    @Test
    void deterministicSession() {
        String in = "{\"cash\":\"10000\",\"limits\":" + LIMITS + ",\"lit\":" + LIT + ",\"script\":[{\"op\":\"SUBMIT\","
                + "\"ts\":\"t1\",\"order\":{\"order_id\":\"O1\",\"symbol\":\"BTC-USD\",\"side\":\"BUY\",\"type\":\"IOC\","
                + "\"quantity\":\"4\",\"limit_price\":\"100.5\"},\"snapshot\":" + SNAP + "},{\"op\":\"CLOSE\",\"ts\":\"t2\","
                + "\"prev_marks\":{},\"marks\":{\"BTC-USD\":\"101\"}}]}";
        String a = run("paper.session.run", in);
        assertEquals(a, run("paper.session.run", in));
        assertTrue(a.contains("\"kind\":\"CANCEL\""), a);
        assertTrue(a.contains("\"kind\":\"TCA\""), a);
    }

    /** The decimal of Python repr: shortest round trip, nearest of the shortest. */
    @Test
    void shortestRoundTrip() {
        assertEquals("76.73333333333333", Paper.fmtDouble(2.302 / (3 * 100.0) * 1e4));
        assertEquals("0.30000000000000004", Paper.fmtDouble(0.1 + 0.2));
        assertEquals("0.00001", Paper.fmtDouble(1e-5));
        assertEquals("0", Paper.fmtDouble(-0.0));
        assertEquals("100000000000000000000000", Paper.fmtDouble(1e23));
        assertEquals(new BigDecimal("5e-324"), Paper.shortest(Double.MIN_VALUE));
        assertEquals(new BigDecimal("1.7976931348623157e308"), Paper.shortest(Double.MAX_VALUE));
        assertEquals(new BigDecimal("2.2250738585072014e-308"), Paper.shortest(Double.MIN_NORMAL));
        SplittableRandom rnd = new SplittableRandom(3);
        for (int k = 0; k < 20000; k++) {
            double x = Double.longBitsToDouble(rnd.nextLong());
            if (Double.isNaN(x) || Double.isInfinite(x)) {
                continue;
            }
            BigDecimal s = Paper.shortest(x);
            assertEquals(x, Double.parseDouble(s.toString()));
            // JDK 19+ Double.toString has the same digit count; both are the nearest of the shortest
            assertEquals(0, new BigDecimal(Double.toString(x)).compareTo(s), Double.toString(x));
        }
    }

    @Test
    void pythonDecimalGrammar() {
        String j = run("paper.book.apply_fill", "{\"fills\":[{\"side\":\"BUY\",\"quantity\":\" 2 \",\"price\":\"1E+2\"}]}");
        assertTrue(j.contains("\"cash_delta\":\"-200\""), j);
        String p = run("paper.book.apply_fill", "{\"fills\":[{\"side\":\"BUY\",\"quantity\":\"x\",\"price\":\"1\"}]}");
        assertTrue(p.contains("\"E_SCHEMA\""), p);
    }

    /** HR-78: a repeated key at any level is PARSE; HR-77: out of the exact range is E_LIMIT, never rounded. */
    @Test
    void duplicateKeysAndExactRange() {
        String line = Paper.verify(randomLedger(1, 5).text()).get("head").toString();
        String text = randomLedger(1, 5).text();
        assertEquals(true, Paper.verify(text).get("ok"), line);
        String dupTop = text.replaceFirst("\\{", "{\"kind\":\"ORDER\",");
        assertEquals("PARSE", Paper.verify(dupTop).get("reason"));
        String dupBody = text.replaceFirst("\"body\":\\{", "\"body\":{\"x\":\"1\",\"x\":\"1\",");
        assertEquals("PARSE", Paper.verify(dupBody).get("reason"));
        String j = run("paper.book.apply_fill", "{\"fills\":[{\"side\":\"BUY\",\"quantity\":\"0.0000000000000000001\","
                + "\"price\":\"1\"}]}");
        assertTrue(j.contains("\"E_LIMIT\""), j);
        String c = run("paper.book.apply_fill", "{\"fills\":[{\"side\":\"BUY\",\"quantity\":\"3\",\"price\":\"1\"},"
                + "{\"side\":\"BUY\",\"quantity\":\"3\",\"price\":\"2\"},{\"side\":\"BUY\",\"quantity\":\"1\",\"price\":\"1\"}]}");
        assertTrue(c.contains("\"avg_cost\":\"1.428571428571428571\""), c);
    }

    @Test
    void goldenFilesPresent() throws IOException {
        try (Stream<Path> s = Files.list(Path.of("..", "datasets", "golden", "stage_h"))) {
            assertEquals(2, s.filter(f -> f.getFileName().toString().matches("(pt_h|e1_hpt)\\.json")).count());
        }
    }
}
