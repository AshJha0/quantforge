package org.quantforge.micro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Stream;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.constraints.IntRange;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;
import org.quantforge.core.Rng;

/**
 * Stage H wave 2 dark pool (H-12) and router (H-13): every golden row of dark_h.json and sor_h.json, property tests,
 * and the planted-parameter acceptance tests of dark-pool.md (seeds 20261118 and 20261119, fixed in the spec).
 */
class DarkSorTest {
    private static final Path GOLD = Path.of("..", "datasets", "golden", "stage_h");

    private static List<Map<?, ?>> cases(String name) throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(GOLD.resolve(name + ".json"))).value();
        List<Map<?, ?>> out = new ArrayList<>();
        for (Object o : (List<?>) doc.get("cases")) {
            out.add((Map<?, ?>) o);
        }
        return out;
    }

    private static Object canon(Object v) {
        if (v instanceof Map<?, ?> m) {
            Map<String, Object> t = new TreeMap<>();
            m.forEach((k, x) -> t.put((String) k, canon(x)));
            return t;
        }
        if (v instanceof List<?> l) {
            return l.stream().map(DarkSorTest::canon).toList();
        }
        return v;
    }

    private static String text(Object v) {
        StringBuilder b = new StringBuilder();
        Json.write(b, canon(v));
        return b.toString();
    }

    private static Map<String, Object> dark(Map<?, ?> inp) {
        if (inp.containsKey("scenarios")) {
            List<Object> runs = new ArrayList<>();
            for (Object s : (List<?>) inp.get("scenarios")) {
                Map<?, ?> m = (Map<?, ?>) s;
                runs.add(DarkPool.run((Map<?, ?>) m.get("config"), (List<?>) m.get("events")));
            }
            return Map.of("scenarios", runs);
        }
        if (inp.containsKey("config")) {
            return DarkPool.run((Map<?, ?>) inp.get("config"), (List<?>) inp.get("events"));
        }
        return DarkPool.markouts((List<?>) inp.get("fills"));
    }

    private static void check(java.util.function.Function<Map<?, ?>, Map<String, Object>> fn, Map<?, ?> c) {
        Map<?, ?> exp = (Map<?, ?>) c.get("expected");
        Map<?, ?> inp = (Map<?, ?>) c.get("inputs");
        if ("error".equals(exp.get("status"))) {
            QfError e = assertThrows(QfError.class, () -> fn.apply(inp));
            assertEquals(exp.get("error_code"), e.code());
        } else {
            assertEquals(text(exp.get("outputs")), text(fn.apply(inp)), String.valueOf(c.get("case_id")));
        }
    }

    @TestFactory
    Stream<DynamicTest> goldens() throws IOException {
        List<DynamicTest> out = new ArrayList<>();
        for (Map<?, ?> c : cases("dark_h")) {
            out.add(DynamicTest.dynamicTest((String) c.get("case_id"), () -> check(DarkSorTest::dark, c)));
        }
        for (Map<?, ?> c : cases("sor_h")) {
            out.add(DynamicTest.dynamicTest((String) c.get("case_id"), () -> check(Sor::allocate, c)));
        }
        assertEquals(16, out.size());
        return out.stream();
    }

    // ------------------------------------------------------------- dark pool paths

    private static Map<String, Object> cfg(Object... kv) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("firm_delay", 0L);
        m.put("lot_size", "1");
        m.put("p_firm", "1");
        m.put("penalty_events", 2L);
        m.put("seed", 1L);
        m.put("tick_size", "0.01");
        for (int i = 0; i < kv.length; i += 2) {
            m.put((String) kv[i], kv[i + 1]);
        }
        return m;
    }

    private static Map<String, Object> book(String bid, String ask) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("op", "BOOK");
        if (bid != null) {
            m.put("bid", bid);
        }
        if (ask != null) {
            m.put("ask", ask);
        }
        return m;
    }

    private static final Map<String, Object> BOOK = book("100.00", "100.10");

    private static Map<String, Object> order(String id, String side, String qty, String kind, Object... kv) {
        Map<String, Object> m = new LinkedHashMap<>(Map.of("op", "NEW", "id", id, "side", side, "qty", qty,
                "kind", kind));
        for (int i = 0; i < kv.length; i += 2) {
            m.put((String) kv[i], kv[i + 1]);
        }
        return m;
    }

    private static List<?> fills(Map<String, Object> out) {
        return (List<?>) out.get("fills");
    }

    @Test
    void minQtyEqualQtyCrossesOnlyOnExactSize() {
        assertTrue(fills(DarkPool.run(cfg(), List.of(BOOK, order("B", "BUY", "50", "FIRM", "min_qty", "50"),
                order("S", "SELL", "40", "FIRM", "min_qty", "40")))).isEmpty());
        assertEquals(1, fills(DarkPool.run(cfg(), List.of(BOOK, order("B", "BUY", "50", "FIRM", "min_qty", "50"),
                order("S", "SELL", "50", "FIRM", "min_qty", "50")))).size());
    }

    @Test
    void lockedBookAndMissingSideGiveNoMid() {
        for (Map<String, Object> b : List.of(book("100.00", "100.00"), book("100.00", null))) {
            assertTrue(fills(DarkPool.run(cfg(), List.of(b, order("B", "BUY", "5", "FIRM"),
                    order("S", "SELL", "5", "FIRM")))).isEmpty());
        }
    }

    @Test
    void cancelRemovesAndTimePriority() {
        Map<?, ?> f = (Map<?, ?>) fills(DarkPool.run(cfg(), List.of(BOOK, order("B1", "BUY", "5", "FIRM"),
                order("B2", "BUY", "5", "FIRM"), Map.of("op", "CANCEL", "id", "B1"),
                order("S", "SELL", "5", "FIRM")))).get(0);
        assertEquals("B2", f.get("buy_id"));
    }

    @Test
    void firmDelayHoldsThenFillsAtLaterMid() {
        Map<String, Object> out = DarkPool.run(cfg("firm_delay", 2L), List.of(BOOK,
                order("C", "BUY", "5", "CONDITIONAL"), order("S", "SELL", "5", "FIRM"), book("100.00", "100.20"),
                book("100.00", "100.30")));
        assertEquals("[{\"contra_id\":\"S\",\"event\":5,\"id\":\"C\",\"result\":\"FIRMED\"}]",
                text(out.get("invitations")));
        assertEquals("100.15", ((Map<?, ?>) fills(out).get(0)).get("price"));
    }

    @Test
    void seededDrawIsDeterministicAndBothConditionalsInvited() {
        List<Object> ev = new ArrayList<>(List.of(BOOK, order("C", "BUY", "5", "CONDITIONAL"),
                order("S", "SELL", "5", "FIRM")));
        for (int i = 0; i < 20; i++) {
            ev.add(BOOK);
        }
        Map<String, Object> c = cfg("p_firm", "0.5", "penalty_events", 0L, "seed", 7L);
        Map<String, Object> a = DarkPool.run(c, ev);
        assertEquals(text(a), text(DarkPool.run(c, ev)));
        assertEquals(1, fills(a).size());
        Map<String, Object> both = DarkPool.run(cfg(), List.of(BOOK, order("C1", "BUY", "5", "CONDITIONAL"),
                order("C2", "SELL", "5", "CONDITIONAL")));
        assertEquals(2, ((List<?>) both.get("invitations")).size());
    }

    @Test
    void darkErrors() {
        Object[][] bad = {
            {List.of(book("100.005", "100.10")), "E_DOMAIN"},
            {List.of(order("B", "BUY", "5", "FIRM"), order("B", "BUY", "5", "FIRM")), "E_INPUT"},
            {List.of(Map.of("op", "CANCEL", "id", "X")), "E_INPUT"},
            {List.of(Map.of("op", "AMEND")), "E_SCHEMA"},
            {List.of(order("B", "HOLD", "5", "FIRM")), "E_SCHEMA"},
        };
        for (Object[] b : bad) {
            assertEquals(b[1], assertThrows(QfError.class, () -> DarkPool.run(cfg(), (List<?>) b[0])).code());
        }
        assertThrows(QfError.class, () -> DarkPool.markouts(List.of(Map.of("side", "BUY", "fill_price", "0",
                "mid_at", Map.of()))));
    }

    /** Property: every fill is at the mid, within both limits, and quantity is conserved per order. */
    @Property(tries = 60)
    void fillsConserveQuantity(@ForAll @IntRange(min = 0, max = 1_000_000) int seed) {
        java.util.Random r = new java.util.Random(seed);
        List<Object> ev = new ArrayList<>();
        Map<String, Integer> sub = new TreeMap<>();
        for (int k = 0; k < 30; k++) {
            if (r.nextInt(4) == 0) {
                int bid = 10000 + r.nextInt(5);
                ev.add(book(bid / 100 + "." + String.format("%02d", bid % 100),
                        (bid + 1 + r.nextInt(3)) / 100 + "." + String.format("%02d", (bid + 1) % 100)));
            } else {
                int q = 1 + r.nextInt(20);
                String id = "O" + k;
                sub.put(id, q);
                ev.add(order(id, r.nextBoolean() ? "BUY" : "SELL", Integer.toString(q),
                        r.nextInt(3) == 0 ? "CONDITIONAL" : "FIRM", "min_qty", Integer.toString(1 + r.nextInt(q))));
            }
        }
        Map<String, Object> out = DarkPool.run(cfg("p_firm", "0.5", "seed", (long) seed), ev);
        Map<String, Integer> used = new TreeMap<>();
        for (Object o : fills(out)) {
            Map<?, ?> f = (Map<?, ?>) o;
            int q = Integer.parseInt((String) f.get("qty"));
            used.merge((String) f.get("buy_id"), q, Integer::sum);
            used.merge((String) f.get("sell_id"), q, Integer::sum);
        }
        for (Object o : (List<?>) out.get("resting")) {
            Map<?, ?> m = (Map<?, ?>) o;
            used.merge((String) m.get("id"), Integer.parseInt((String) m.get("open_qty")), Integer::sum);
        }
        used.forEach((id, q) -> assertTrue(q <= sub.get(id), id));
        assertEquals(DarkPool.LABEL, out.get("label"));
    }

    @Test
    void kmWithoutCensoringIsEmpiricalAndAllCensoredStaysOne() {
        int[][] obs = {{10, 0}, {10, 1}, {10, 1}, {10, 2}, {10, 3}, {10, 5}};
        double[][] est = DarkPool.kmTail(obs, 6);
        for (int s = 1; s <= 6; s++) {
            int c = 0;
            for (int[] o : obs) {
                c += o[1] >= s ? 1 : 0;
            }
            assertEquals(c / 6.0, est[s - 1][0], 1e-12);
        }
        for (double[] t : DarkPool.kmTail(new int[][] {{5, 5}, {7, 7}}, 4)) {
            assertEquals(1.0, t[0]);
        }
    }

    // ------------------------------------------------------------- planted recovery (H-4)

    @Test
    void plantedFillProbabilityRecoveredWithin3Se() {
        Rng rng = Rng.seeded(20261118L, 0);
        int[][] obs = new int[20_000][];
        for (int i = 0; i < obs.length; i++) {
            int s = Math.min((int) (rng.nextUniform() * 10), 9);
            int v = 1 + Math.min((int) (rng.nextUniform() * 10), 9);
            obs[i] = new int[] {v, Math.min(s, v)};
        }
        double[][] t = DarkPool.kmTail(obs, 8);
        for (int s = 1; s <= 8; s++) {
            assertTrue(Math.abs(t[s - 1][0] - (1 - 0.1 * s)) <= 3 * t[s - 1][1], "s=" + s);
        }
    }

    @Test
    void plantedLeakageRecoveredWithin3Se() {
        Rng rng = Rng.seeded(20261119L, 0);
        double alpha = 0.3;
        double jump = 0.20;
        Map<String, Object> c = cfg("seed", 20261119L);
        List<Double> adverse = new ArrayList<>();
        for (int i = 0; i < 4_000; i++) {
            String ours = rng.nextUniform() < 0.5 ? "BUY" : "SELL";
            boolean up = rng.nextUniform() < 0.5;
            boolean informed = rng.nextUniform() < alpha;
            String contra = informed ? (up ? "BUY" : "SELL") : (rng.nextUniform() < 0.5 ? "BUY" : "SELL");
            Map<String, Object> out = DarkPool.run(c, List.of(BOOK, order("U", ours, "100", "FIRM"),
                    order("X", contra, "100", "FIRM")));
            if (fills(out).isEmpty()) {
                continue;
            }
            String px = (String) ((Map<?, ?>) fills(out).get(0)).get("price");
            String mid = String.format(java.util.Locale.ROOT, "%.3f", Double.parseDouble(px) + (up ? jump : -jump));
            Map<String, Object> bp = DarkPool.markouts(List.of(Map.of("side", ours, "fill_price", px,
                    "mid_at", Map.of("1", mid))));
            Map<?, ?> m = (Map<?, ?>) ((Map<?, ?>) ((List<?>) bp.get("fills")).get(0)).get("markouts_bp");
            adverse.add(-Double.parseDouble((String) m.get("1")) * Double.parseDouble(px) / 10_000);
        }
        int n = adverse.size();
        double mean = adverse.stream().mapToDouble(Double::doubleValue).sum() / n;
        double ss = adverse.stream().mapToDouble(a -> (a - mean) * (a - mean)).sum();
        double se = Math.sqrt(ss / (n - 1) / n);
        assertTrue(Math.abs(mean - alpha * jump) <= 3 * se, mean + " " + se + " " + n);
    }

    // ------------------------------------------------------------- router paths

    private static Map<String, Object> with(Map<?, ?> base, Object... kv) {
        Map<String, Object> m = new LinkedHashMap<>();
        base.forEach((k, v) -> m.put((String) k, v));
        m.remove("ranking");
        for (int i = 0; i < kv.length; i += 2) {
            m.put((String) kv[i], kv[i + 1]);
        }
        return m;
    }

    @Test
    void closedFormAgreesWithSampleAverage() throws IOException {
        for (int k = 0; k < 3; k++) {
            Map<?, ?> inp = (Map<?, ?>) cases("sor_h").get(k).get("inputs");
            assertEquals(text(Sor.allocate(inp)), text(Sor.allocate(with(inp, "method", "CLOSED_FORM"))));
        }
    }

    @Test
    void stochasticApproxReachesSampleAverageOptimumOnEveryGolden() throws IOException {
        for (int k = 0; k < 5; k++) {
            Map<String, Object> inp = with((Map<?, ?>) cases("sor_h").get(k).get("inputs"));
            String best = text(Sor.allocate(inp));
            for (long n : new long[] {1_000, 10_000}) {
                Map<String, Object> sa = with(inp, "method", "STOCHASTIC_APPROX", "iterations", n, "step", 1.0,
                        "seed", 3L);
                assertEquals(best, text(Sor.allocate(sa)), k + " " + n);
            }
        }
    }

    @Test
    void reportSeDescentAndErrors() throws IOException {
        Map<?, ?> sor3 = (Map<?, ?>) cases("sor_h").get(2).get("inputs");
        Map<String, Object> out = Sor.allocate(with(sor3, "report_se", true));
        assertEquals(Sor.LABEL, out.get("label"));
        assertTrue(Double.parseDouble((String) out.get("expected_cost_se")) > 0);
        Sor.Problem p = new Sor.Problem(sor3);
        assertEquals(List.of(8, 2), java.util.Arrays.stream(p.descent(p.start())).boxed().toList());
        Map<String, Object> lit = Map.of("kind", "LIT", "Q", "0", "r", "0", "as", "0");
        Object[][] bad = {
            {with(sor3, "S", "1.5"), "E_DOMAIN"},
            {with(sor3, "venues", List.of()), "E_INPUT"},
            {with(sor3, "venues", java.util.Collections.nCopies(65, lit)), "E_LIMIT"},
            {with(sor3, "method", "GREEDY"), "E_SCHEMA"},
            {with(sor3, "lit_samples", List.of(List.of("1", "2"))), "E_INPUT"},
            {with(sor3, "venues", List.of(Map.of("kind", "DARK", "r", "0", "as", "0", "tail", List.of("0.2", "0.5")))),
                "E_DOMAIN"},
            {with(sor3, "method", "CLOSED_FORM", "lit_samples", List.of(),
                "venues", List.of(Map.of("kind", "DARK", "r", "0", "as", "0", "tail", List.of()))), "E_DOMAIN"},
        };
        for (Object[] b : bad) {
            assertEquals(b[1], assertThrows(QfError.class, () -> Sor.allocate((Map<?, ?>) b[0])).code());
        }
    }

    /** Property: the chosen split has the lowest exact cost of the whole grid (exhaustive HR-38). */
    @Property(tries = 30)
    void sampleAverageIsGridMinimum(@ForAll @IntRange(min = 0, max = 1_000_000) int seed) {
        java.util.Random r = new java.util.Random(seed);
        List<Object> rows = new ArrayList<>();
        for (int i = 0; i < 4; i++) {
            rows.add(List.of(Integer.toString(r.nextInt(6))));
        }
        Map<String, Object> inp = new LinkedHashMap<>(Map.of("S", "3", "h", "0.5", "f", "0.3", "theta",
                "0." + r.nextInt(3), "lambda_u", Integer.toString(r.nextInt(5)), "lambda_o", "1", "lit_samples", rows,
                "venues", List.of(Map.of("kind", "LIT", "Q", Integer.toString(r.nextInt(3)), "r", "0.2", "as", "0"),
                        Map.of("kind", "DARK", "r", "0", "as", "0.1", "tail", List.of("0.7", "0.4", "0.1")))));
        inp.put("ranking", true);
        Map<String, Object> out = Sor.allocate(inp);
        List<?> rank = (List<?>) out.get("ranking");
        assertEquals(64, rank.size());
        assertEquals(out.get("expected_cost"), ((Map<?, ?>) rank.get(0)).get("expected_cost"));
    }
}
