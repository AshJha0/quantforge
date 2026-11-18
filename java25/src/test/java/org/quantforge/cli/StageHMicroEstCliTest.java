package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * Stage H H-4b and H-16 through the CLI: every {@code mest_h} and {@code venue_h} golden row (value and error code),
 * then the paths the goldens miss, as {@code python/tests/test_stage_h_micro.py} checks them.
 */
class StageHMicroEstCliTest {
    private static final Path GOLD = Path.of("..", "datasets", "golden", "stage_h");

    private static Map<?, ?> run(String op, String inputs) {
        String json = Main.handle("{\"schema_version\":\"1.0\",\"case_id\":\"c\",\"operation\":\"" + op
                + "\",\"inputs\":" + inputs + "}").json();
        return (Map<?, ?>) Json.parse(json).value();
    }

    private static String code(String op, String inputs) {
        Map<?, ?> r = run(op, inputs);
        assertEquals("error", r.get("status"), r::toString);
        return (String) ((Map<?, ?>) r.get("error")).get("code");
    }

    private static Map<?, ?> ok(String op, String inputs) {
        Map<?, ?> r = run(op, inputs);
        assertEquals("ok", r.get("status"), r::toString);
        return (Map<?, ?>) r.get("outputs");
    }

    private static double num(Object o) {
        return ((Json.Number) o).value();
    }

    private static void close(Object a, Object e, String path) {
        if (e instanceof Map<?, ?> em) {
            Map<?, ?> am = (Map<?, ?>) a;
            assertEquals(em.keySet(), am.keySet(), path);
            assertEquals(List.copyOf(em.keySet()), List.copyOf(am.keySet()), path + " key order");
            em.forEach((k, v) -> close(am.get(k), v, path + "." + k));
        } else if (e instanceof List<?> el) {
            List<?> al = (List<?>) a;
            assertEquals(el.size(), al.size(), path);
            for (int i = 0; i < el.size(); i++) {
                close(al.get(i), el.get(i), path + "[" + i + "]");
            }
        } else if (e instanceof Json.Number en) {
            double x = num(a);
            double y = en.value();
            assertTrue(Math.abs(x - y) <= 1e-15 + 1e-12 * Math.max(Math.abs(x), Math.abs(y)), path + ": " + x + " vs " + y);
        } else {
            assertEquals(e, a, path);
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"mest_h", "venue_h"})
    void everyGoldenRow(String suite) throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(GOLD.resolve(suite + ".json"))).value();
        int n = 0;
        for (Object o : (List<?>) doc.get("cases")) {
            Map<?, ?> c = (Map<?, ?>) o;
            String op = (String) c.get("operation");
            assertNotNull(Operations.find(op), op);
            Map<String, Object> env = new LinkedHashMap<>();
            env.put("schema_version", "1.0");
            env.put("case_id", c.get("case_id"));
            env.put("operation", op);
            env.put("inputs", c.get("inputs"));
            StringBuilder b = new StringBuilder();
            Json.write(b, env);
            Map<?, ?> r = (Map<?, ?>) Json.parse(Main.handle(b.toString()).json()).value();
            Map<?, ?> exp = (Map<?, ?>) c.get("expected");
            String id = (String) c.get("case_id");
            assertEquals(exp.get("status"), r.get("status"), id + " " + r);
            if ("error".equals(exp.get("status"))) {
                assertEquals(exp.get("error_code"), ((Map<?, ?>) r.get("error")).get("code"), id);
            } else {
                close(r.get("outputs"), exp.get("outputs"), id);
            }
            n++;
        }
        assertTrue(n >= 8, suite);
    }

    @Test
    void schemaAndNonFinite() {
        assertEquals("E_SCHEMA", code("micro.est.arrival_rate", "{\"count\":1.5,\"window\":1.0}"));
        assertEquals("E_SCHEMA", code("micro.est.cancel_rate", "{\"orders\":[{\"lifetime\":1.0,\"outcome\":\"EXPIRE\"}]}"));
        assertEquals("E_DOMAIN", code("micro.est.passive_vs_aggressive",
                "{\"passive\":[1.0,\"Infinity\"],\"aggressive\":[1.0,2.0]}"));
        assertEquals("E_DOMAIN", code("micro.est.arrival_rate", "{\"count\":-1,\"window\":1.0}"));
        Map<?, ?> zero = ok("micro.est.arrival_rate", "{\"count\":0,\"window\":2.0}");
        assertEquals(0.0, num(zero.get("lambda")));
        assertEquals(0.0, num(zero.get("se")));
        assertEquals("E_SCHEMA", code("micro.est.regime_impact", "{\"regimes\":{\"calm\":3}}"));
    }

    @Test
    void estimatorErrorOrder() {
        assertEquals("E_DOMAIN", code("micro.est.cancel_rate", "{\"orders\":[{\"lifetime\":0.0,\"outcome\":\"CANCEL\"}]}"));
        assertEquals("E_INPUT", code("micro.est.cancel_rate", "{\"orders\":[{\"lifetime\":1.0,\"outcome\":\"FILL\"}]}"));
        assertEquals("E_INPUT", code("micro.est.resilience",
                "{\"s_inf\":1.0,\"points\":[{\"t\":0,\"s\":2.0},{\"t\":0,\"s\":3.0},{\"t\":0,\"s\":4.0}]}"));
        assertEquals("E_DOMAIN", code("micro.est.resilience",
                "{\"s_inf\":1.0,\"points\":[{\"t\":0,\"s\":2.0},{\"t\":1,\"s\":0.5},{\"t\":2,\"s\":4.0}]}"));
        assertEquals("E_DOMAIN", code("micro.est.liquidity_decay",
                "{\"levels\":[{\"k\":0,\"depth\":1.0},{\"k\":1,\"depth\":0.0},{\"k\":2,\"depth\":1.0}]}"));
        assertEquals("E_INPUT", code("micro.est.liquidity_decay",
                "{\"levels\":[{\"k\":0,\"depth\":1.0},{\"k\":1,\"depth\":0.0}]}")); // HR-75 as amended (HR-66)
        assertEquals("E_INPUT", code("micro.est.adverse_selection", "{\"x\":[1.0],\"y\":[1.0,2.0]}"));
        assertEquals("E_INPUT", code("micro.est.adverse_selection", "{\"x\":[0.0,0.0],\"y\":[1.0,2.0]}"));
        String good = "{\"x\":[1.0,2.0],\"y\":[1.0,2.0]}";
        assertEquals("E_INPUT", code("micro.est.regime_impact", "{\"regimes\":{\"calm\":" + good + "}}"));
        assertEquals("E_INPUT", code("micro.est.regime_impact",
                "{\"regimes\":{\"calm\":" + good + ",\"stressed\":{\"x\":[1.0],\"y\":[1.0]}}}"));
        assertEquals("E_DOMAIN", code("micro.est.regime_impact",
                "{\"regimes\":{\"calm\":{\"x\":[1.0,-1.0],\"y\":[1.0,1.0]},\"stressed\":" + good + "}}"));
        assertEquals("E_INPUT", code("micro.est.passive_vs_aggressive", "{\"passive\":[1.0,2.0],\"aggressive\":[1.0]}"));
        assertEquals("E_INPUT", code("micro.est.passive_vs_aggressive", "{\"passive\":[1.0],\"aggressive\":[1.0,2.0]}"));
        Map<?, ?> r = ok("micro.est.regime_impact",
                "{\"regimes\":{\"stressed\":" + good + ",\"calm\":" + good + ",\"B\":" + good + "}}");
        assertEquals(List.of("B", "calm", "stressed"), List.copyOf(((Map<?, ?>) r.get("regimes")).keySet()));
    }

    private static final String MIDS = "[{\"t\":0.0,\"mid\":100.0},{\"t\":1.0,\"mid\":100.02},{\"t\":5.0,\"mid\":100.05},"
            + "{\"t\":10.0,\"mid\":99.98}]";
    private static final String FILLS = "[{\"venue\":\"A\",\"side\":\"BUY\",\"quantity\":100.0,\"price\":100.01,\"t\":0.0},"
            + "{\"venue\":\"A\",\"side\":\"SELL\",\"quantity\":200.0,\"price\":100.03,\"t\":1.0},"
            + "{\"venue\":\"B\",\"side\":\"BUY\",\"quantity\":300.0,\"price\":100.0,\"t\":1.0}]";
    private static final String ORDERS = "[{\"venue\":\"A\",\"sent\":500.0,\"filled\":300.0},"
            + "{\"venue\":\"B\",\"sent\":300.0,\"filled\":300.0}]";

    private static String venue(String mids, String fills, String orders, String horizons) {
        return "{\"mids\":" + mids + ",\"fills\":" + fills + ",\"orders\":" + orders + ",\"horizons\":" + horizons + "}";
    }

    @Test
    void venueErrors() {
        String op = "exec.venue.analytics";
        assertEquals("E_INPUT", code(op, venue("[{\"t\":1.0,\"mid\":100.0},{\"t\":0.0,\"mid\":100.0}]", FILLS, ORDERS, "[5.0]")));
        assertEquals("E_DOMAIN", code(op, venue("[{\"t\":0.0,\"mid\":0.0}]", FILLS, ORDERS, "[5.0]")));
        String f = "{\"venue\":\"A\",\"side\":\"BUY\",\"quantity\":100.0,\"price\":%s,\"t\":0.0}";
        assertEquals("E_DOMAIN", code(op, venue(MIDS, "[" + f.formatted("0.0") + "]", ORDERS, "[5.0]")));
        assertEquals("E_DOMAIN", code(op, venue(MIDS,
                "[{\"venue\":\"A\",\"side\":\"BUY\",\"quantity\":-1.0,\"price\":1.0,\"t\":0.0}]", ORDERS, "[5.0]")));
        assertEquals("E_DOMAIN", code(op, venue(MIDS, FILLS, "[{\"venue\":\"A\",\"sent\":0.0,\"filled\":0.0}]", "[5.0]")));
        assertEquals("E_DOMAIN", code(op, venue(MIDS, FILLS, "[{\"venue\":\"A\",\"sent\":1.0,\"filled\":-1.0}]", "[5.0]")));
        assertEquals("E_INPUT", code(op, venue(MIDS, FILLS, "[{\"venue\":\"A\",\"sent\":1.0,\"filled\":2.0}]", "[5.0]")));
        assertEquals("E_DOMAIN", code(op, venue(MIDS, FILLS, ORDERS, "[-1.0]")));
        assertEquals("E_INPUT", code(op, venue("[{\"t\":2.0,\"mid\":100.0}]", FILLS, ORDERS, "[0.0]")));
        assertEquals("E_SCHEMA", code(op, venue(MIDS,
                "[{\"venue\":\"A\",\"side\":\"HOLD\",\"quantity\":1.0,\"price\":1.0,\"t\":0.0}]", ORDERS, "[5.0]")));
        Map<?, ?> empty = ok(op, venue(MIDS, "[]", "[]", "[5.0]"));
        assertTrue(((Map<?, ?>) empty.get("fill_rates")).isEmpty());
        assertTrue(((List<?>) empty.get("markouts")).isEmpty());
    }

    @ParameterizedTest
    @ValueSource(doubles = {0.0, 0.5, 1.0, 4.0, 5.0, 9.0, 10.0, 100.0})
    void venueProperties(double h) {
        List<?> a = (List<?>) ok("exec.venue.analytics", venue(MIDS, FILLS, ORDERS, "[" + h + "]")).get("markouts");
        // mirror every price about c = 120 and swap the sides: the markouts are unchanged
        String mids2 = "[{\"t\":0.0,\"mid\":140.0},{\"t\":1.0,\"mid\":139.98},{\"t\":5.0,\"mid\":139.95},"
                + "{\"t\":10.0,\"mid\":140.02}]";
        String fills2 = "[{\"venue\":\"A\",\"side\":\"SELL\",\"quantity\":100.0,\"price\":139.99,\"t\":0.0},"
                + "{\"venue\":\"A\",\"side\":\"BUY\",\"quantity\":200.0,\"price\":139.97,\"t\":1.0},"
                + "{\"venue\":\"B\",\"side\":\"SELL\",\"quantity\":300.0,\"price\":140.0,\"t\":1.0}]";
        List<?> b = (List<?>) ok("exec.venue.analytics", venue(mids2, fills2, ORDERS, "[" + h + "]")).get("markouts");
        for (int i = 0; i < a.size(); i++) {
            Map<?, ?> r = (Map<?, ?>) a.get(i);
            Map<?, ?> r2 = (Map<?, ?>) b.get(i);
            double tox = num(r.get("toxicity"));
            assertTrue(tox >= 0 && tox <= 1);
            double m = num(r.get("markout"));
            assertTrue(m == 0 || Math.signum(m) == Math.signum(num(r.get("markout_bps"))));
            assertTrue(Math.abs(m - num(r2.get("markout"))) <= 1e-12);
        }
    }

    @Test
    void venueSingleFill() {
        Map<?, ?> r = ok("exec.venue.analytics", venue("[{\"t\":0.0,\"mid\":101.0}]",
                "[{\"venue\":\"A\",\"side\":\"BUY\",\"quantity\":1.0,\"price\":100.0,\"t\":0.0}]",
                "[{\"venue\":\"A\",\"sent\":2.0,\"filled\":1.0}]", "[0.0]"));
        assertEquals(0.5, num(((Map<?, ?>) r.get("fill_rates")).get("A")));
        Map<?, ?> m = (Map<?, ?>) ((List<?>) r.get("markouts")).getFirst();
        assertEquals(1.0, num(m.get("markout")));
        assertEquals(100.0, num(m.get("markout_bps")));
        assertEquals(0.0, num(m.get("toxicity")));
    }
}
