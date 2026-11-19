package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;

/**
 * Stage K wave 1 through the CLI: registration, every golden row with its own tolerance (the Python test's), the
 * HR-66 error order, the finite rule, the K-4 property on the stage B sequential bootstraps and the KR-8
 * {@code method} input.
 */
class StageKCliTest {
    private static final Path GOLD = Path.of("..", "datasets", "golden");

    private static String run(String op, String inputs) {
        return Main.handle("{\"schema_version\":\"1.0\",\"case_id\":\"c\",\"operation\":\"" + op
                + "\",\"inputs\":" + inputs + "}").json();
    }

    private static Map<?, ?> runMap(String op, Object inputs) {
        Map<String, Object> env = new LinkedHashMap<>();
        env.put("schema_version", "1.0");
        env.put("case_id", "c");
        env.put("operation", op);
        env.put("inputs", inputs);
        StringBuilder b = new StringBuilder();
        Json.write(b, env);
        return (Map<?, ?>) Json.parse(Main.handle(b.toString()).json()).value();
    }

    private static String code(String op, String inputs) {
        String out = run(op, inputs);
        assertTrue(out.contains("\"status\":\"error\""), out);
        int i = out.indexOf("\"code\":\"") + 8;
        return out.substring(i, out.indexOf('"', i));
    }

    private static List<?> cases(String suite) throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(GOLD.resolve(suite))).value();
        return (List<?>) doc.get("cases");
    }

    private static double num(Object o) {
        return ((Json.Number) o).value();
    }

    private static double rel(double a, double b) {
        return Math.abs(a - b) / Math.max(Math.max(Math.abs(a), Math.abs(b)), 1e-300);
    }

    @Test
    void operationsRegistered() {
        for (String op : OpsStageK.OPERATIONS) {
            assertNotNull(Operations.find(op), op);
            assertFalse(In.pageLimited(op)); // KR-231: the generic limits apply
        }
    }

    /** Every golden row of the six stage K suites, with the Python test's tolerances. */
    @Test
    void everyGoldenRow() throws IOException {
        int rows = 0;
        for (String s : new String[] {"bt_k", "inc_k", "trig_k", "idr_k", "rich_k", "e1_k"}) {
            for (Object o : cases("stage_k/" + s + ".json")) {
                Map<?, ?> c = (Map<?, ?>) o;
                Map<?, ?> want = (Map<?, ?>) c.get("expected");
                Map<?, ?> got = runMap((String) c.get("operation"), c.get("inputs"));
                String id = (String) c.get("case_id");
                assertEquals(want.get("status"), got.get("status"), id + " " + got);
                rows++;
                if ("error".equals(want.get("status"))) {
                    assertEquals(want.get("error_code"), ((Map<?, ?>) got.get("error")).get("code"), id);
                    continue;
                }
                Map<?, ?> w = (Map<?, ?>) want.get("outputs");
                Map<?, ?> g = (Map<?, ?>) got.get("outputs");
                assertEquals(w.keySet(), g.keySet(), id);
                // KR-240: a cancelling idr case carries an absolute tolerance_limit, the derived rounding share
                double extra = c.get("tolerance_limit") instanceof Map<?, ?> lim
                        && lim.get("absolute") instanceof Json.Number an ? an.value() : 0.0;
                for (Object key : w.keySet()) {
                    Object wv = w.get(key);
                    if (extra > 0 && wv instanceof Json.Number wn && g.get(key) instanceof Json.Number gn
                            && Math.abs(wn.value() - gn.value()) <= extra + 1e-9 * Math.abs(wn.value())) {
                        continue;
                    }
                    compare(id + "." + key, wv, g.get(key), s.equals("idr_k") ? 1e-9 : 1e-12);
                }
            }
        }
        assertTrue(rows >= 46, "rows " + rows);  // a minimum: adding goldens must not break this test
    }

    /** The shared goldens of the K-8 method (k8_k): values at 1e-9 of the row scale, error codes exactly. */
    @Test
    void k8GoldenRows() throws IOException {
        int rows = 0;
        for (Object o : cases("stage_k/k8_k.json")) {
            Map<?, ?> c = (Map<?, ?>) o;
            Map<?, ?> want = (Map<?, ?>) c.get("expected");
            Map<?, ?> got = runMap((String) c.get("operation"), c.get("inputs"));
            String id = (String) c.get("case_id");
            assertEquals(want.get("status"), got.get("status"), id + " " + got);
            rows++;
            if ("error".equals(want.get("status"))) {
                assertEquals(want.get("error_code"), ((Map<?, ?>) got.get("error")).get("code"), id);
                continue;
            }
            Map<?, ?> w = (Map<?, ?>) want.get("outputs");
            Map<?, ?> g = (Map<?, ?>) got.get("outputs");
            assertEquals(w.keySet(), g.keySet(), id);
            assertTrue(rel(num(w.get("price")), num(g.get("price"))) <= 1e-9, id + ".price");
            if (w.containsKey("d_price_d_discount_factors")) {
                List<?> wl = (List<?>) w.get("d_price_d_discount_factors");
                List<?> gl = (List<?>) g.get("d_price_d_discount_factors");
                assertEquals(wl.size(), gl.size(), id);
                double scale = 0;
                for (Object x : wl) {
                    scale = Math.max(scale, Math.abs(num(x)));
                }
                for (int i = 0; i < wl.size(); i++) {
                    assertTrue(Math.abs(num(wl.get(i)) - num(gl.get(i))) <= 1e-9 * scale, id + "/" + i);
                }
                for (String key : new String[] {"d_price_d_mean_reversion", "d_price_d_sigma"}) {
                    assertTrue(rel(num(w.get(key)), num(g.get(key))) <= 1e-9, id + "." + key);
                }
            }
        }
        assertEquals(14, rows);
    }

    private static void compare(String where, Object want, Object got, double tol) {
        if (want instanceof Json.Number wn) {
            assertTrue(got instanceof Json.Number, where);
            assertTrue(rel(wn.value(), num(got)) <= tol || Math.abs(wn.value() - num(got)) <= 1e-15,
                    where + ": " + got + " vs " + want);
        } else if (want instanceof List<?> wl) {
            List<?> gl = (List<?>) got;
            assertEquals(wl.size(), gl.size(), where);
            for (int i = 0; i < wl.size(); i++) {
                compare(where + "/" + i, wl.get(i), gl.get(i), tol);
            }
        } else if (want instanceof Map<?, ?> wm) {
            Map<?, ?> gm = (Map<?, ?>) got;
            assertEquals(wm.keySet(), gm.keySet(), where);
            for (Object k : wm.keySet()) {
                compare(where + "." + k, wm.get(k), gm.get(k), tol);
            }
        } else {
            assertEquals(want, got, where);
        }
    }

    private static final String REC = "{\"sequence\":1,\"series_id\":\"A\",\"valid_from\":\"2026-01-01T00:00:00Z\","
            + "\"valid_to\":null,\"knowledge_time\":\"2026-01-02T00:00:00Z\",\"value\":100}";

    private static String bt(String records) {
        return "{\"records\":[" + records + "],\"series_id\":\"A\",\"knowledge_as_of\":\"2026-03-15T00:00:00Z\","
                + "\"valid_at\":\"2026-02-15T00:00:00Z\"}";
    }

    @Test
    void bitemporalSchemaOrderAndOutput() {
        assertEquals("E_SCHEMA", code("core.store.bitemporal_query", bt(REC.replace("\"valid_to\":null,", ""))));
        assertEquals("E_SCHEMA", code("core.store.bitemporal_query", bt(REC.replace(",\"value\":100", ""))));
        assertEquals("E_SCHEMA", code("core.store.bitemporal_query", bt(REC.replace("\"sequence\":1",
                "\"sequence\":0"))));
        assertEquals("E_SCHEMA", code("core.store.bitemporal_query", bt(REC.replace("\"A\"", "\"\""))));
        assertEquals("E_SCHEMA", code("core.store.bitemporal_query", bt("1")));
        assertEquals("E_SCHEMA", code("core.store.bitemporal_query", "{\"records\":5}"));
        // HR-122 (KR-230): the finite rule's E_DOMAIN before a structural E_INPUT (sequence order)
        String nan = REC.replace("\"value\":100", "\"value\":\"NaN\"");
        assertEquals("E_DOMAIN", code("core.store.bitemporal_query", bt(nan + "," + REC)));
        assertEquals("E_INPUT", code("core.store.bitemporal_query", bt(REC + "," + REC)));
        assertEquals("E_DOMAIN", code("core.store.bitemporal_query", bt(nan)));
        String ok = run("core.store.bitemporal_query", bt(REC));
        assertTrue(ok.contains("\"valid_to\":null"), ok);
        assertTrue(ok.contains("\"status\":\"FOUND\""), ok);
        String closed = REC.replace("\"valid_to\":null", "\"valid_to\":\"2026-03-01T00:00:00Z\"")
                .replace("\"value\":100", "\"value\":{\"x\":\"NaN\"}");
        String c = run("core.store.bitemporal_query", bt(closed + ",{\"sequence\":2,\"series_id\":\"A\","
                + "\"valid_from\":\"2026-01-01T00:00:00Z\",\"valid_to\":null,\"knowledge_time\":"
                + "\"2026-04-01T00:00:00Z\",\"value\":null,\"deleted\":true}"));
        assertTrue(c.contains("\"valid_to\":\"2026-03-01T00:00:00Z\"") && c.contains("{\"x\":\"NaN\"}"), c);
        assertTrue(run("core.store.bitemporal_query", bt("")).contains("\"status\":\"NONE\",\"row\":null")
                || run("core.store.bitemporal_query", bt("")).contains("\"row\":null"));
    }

    @Test
    void errorOrderAcrossVerbs() {
        String trig = "{\"changes\":[1.0,-1.0,1.0,-1.0],\"x_ref\":100,\"x_now\":104,\"days_since\":1,\"k\":3";
        // HR-122 (KR-230): E_LIMIT, the finite rule, structural E_INPUT, E_DOMAIN
        assertEquals("E_DOMAIN", code("calib.trigger.check", trig.replace("[1.0,-1.0,1.0,-1.0]", "[1.0]")
                .replace("104", "\"NaN\"") + "}"));
        assertEquals("E_INPUT", code("calib.trigger.check", trig.replace("[1.0,-1.0,1.0,-1.0]", "[1.0]")
                .replace("\"k\":3", "\"k\":-1") + "}"));
        assertEquals("E_DOMAIN", code("calib.trigger.check", trig.replace("\"days_since\":1", "\"days_since\":0.5")
                + "}"));
        String many = String.join(",", Collections.nCopies(50_001, "1.0,-1.0"));
        assertEquals("E_LIMIT", code("calib.trigger.check", trig.replace("1.0,-1.0,1.0,-1.0", many) + "}"));
        assertEquals("E_LIMIT", code("calib.trigger.check", trig.replace("1.0,-1.0,1.0,-1.0", many)
                .replace("\"k\":3", "\"k\":-1").replace("104", "\"NaN\"") + "}"));

        assertEquals("E_DOMAIN", code("risk.intraday.delta_gamma_bound", "{\"positions\":[],\"shift\":\"NaN\"}"));
        assertEquals("E_INPUT", code("risk.intraday.delta_gamma_bound", "{\"positions\":[],\"shift\":0.01}"));
        String pos = "{\"notional\":1.0,\"maturity\":1.0,\"yield\":0.0}";
        assertEquals("E_DOMAIN", code("risk.intraday.delta_gamma_bound", "{\"positions\":[" + pos
                + "],\"shift\":\"NaN\"}"));
        String big = String.join(",", Collections.nCopies(100_001, pos));
        assertEquals("E_LIMIT", code("risk.intraday.delta_gamma_bound", "{\"positions\":[" + big
                + "],\"shift\":0.01}"));
        assertEquals("E_LIMIT", code("risk.intraday.delta_gamma_bound", "{\"positions\":[" + big + ","
                + pos.replace("\"maturity\":1.0", "\"maturity\":0.0") + "],\"shift\":0.01}"));
        String zero = run("risk.intraday.delta_gamma_bound", "{\"positions\":[" + pos + "],\"shift\":0.0}");
        assertTrue(zero.contains("\"estimate_pnl\":0") && zero.contains("\"bound\":0")
                && zero.contains("\"label\":\"latency-aware analytics on simulated data\""), zero);

        assertEquals("E_DOMAIN", code("num.richardson.check", "{\"values\":[1.0],\"ratio\":\"NaN\","
                + "\"assumed_order\":1.0}"));
        assertEquals("E_INPUT", code("curve.bootstrap.par_annual", "{\"quotes\":[]}"));
        assertEquals("E_LIMIT", code("curve.bootstrap.par_annual", "{\"quotes\":["
                + String.join(",", Collections.nCopies(201, "0.01")) + "]}"));
        assertEquals("E_DOMAIN", code("curve.incremental.update", "{\"previous_quotes\":[0.01],"
                + "\"previous_discount_factors\":[\"NaN\"],\"new_quotes\":[0.01,0.02]}"));
        assertEquals("E_LIMIT", code("curve.incremental.update", "{\"previous_quotes\":[0.01],"
                + "\"previous_discount_factors\":[\"NaN\"],\"new_quotes\":["
                + String.join(",", Collections.nCopies(201, "0.01")) + "]}"));
        assertEquals("E_LIMIT", code("curve.bootstrap.par_annual", "{\"quotes\":[\"NaN\","
                + String.join(",", Collections.nCopies(200, "-2.0")) + "]}"));
        String rec2 = REC.replace("\"sequence\":1", "\"sequence\":%d");
        StringBuilder log = new StringBuilder();
        for (int i = 100_001; i >= 1; i--) {
            log.append(i == 100_001 ? "" : ",").append(rec2.formatted(i));
        }
        assertEquals("E_LIMIT", code("core.store.bitemporal_query", bt(log.toString())));
        assertEquals("E_SCHEMA", code("curve.incremental.update", "{\"previous_quotes\":[0.01],"
                + "\"previous_discount_factors\":[1],\"new_quotes\":\"x\"}"));
        String upd = run("curve.incremental.update", "{\"previous_quotes\":[0.0],"
                + "\"previous_discount_factors\":[1.0],\"new_quotes\":[0.0]}");
        assertTrue(upd.contains("\"first_changed_index\":null") && upd.contains("\"recomputed\":0"), upd);
    }

    private static List<Object[]> pillars(Map<?, ?> r) {
        List<Object[]> out = new ArrayList<>();
        for (Object o : (List<?>) ((Map<?, ?>) r.get("outputs")).get("pillars")) {
            Map<?, ?> p = (Map<?, ?>) o;
            out.add(new Object[] {p.get("date"), num(p.get("discount_factor"))});
        }
        return out;
    }

    private static boolean same(Object[] a, Object[] b) {
        return a[0].equals(b[0]) && Double.doubleToRawLongBits((Double) a[1]) == Double.doubleToRawLongBits(
                (Double) b[1]);
    }

    /** K-4 on the production sequential bootstraps: a quote change leaves every earlier pillar bit-identical. */
    @Test
    void incrementalPropertyOnStageBBootstraps() throws IOException {
        Random rnd = new Random(7);
        int tried = 0;
        int used = 0;
        for (String name : new String[] {"ois", "ois_deep", "projection", "projection_deep"}) {
            for (Object o : cases("stage_b/" + name + ".json")) {
                Map<?, ?> c = (Map<?, ?>) o;
                Map<?, ?> in = (Map<?, ?>) c.get("inputs");
                String op = (String) c.get("operation");
                if (!op.endsWith(".bootstrap") || !"ok".equals(((Map<?, ?>) c.get("expected")).get("status"))
                        || !"SEQUENTIAL".equals(in.containsKey("method") ? in.get("method") : "SEQUENTIAL")
                        || !"LOG_LINEAR_DF".equals(in.containsKey("interpolation") ? in.get("interpolation")
                                : "LOG_LINEAR_DF")) {
                    continue;
                }
                used++;
                Map<?, ?> base = runMap(op, in);
                assertEquals("ok", base.get("status"));
                assertEquals(base.get("outputs").toString(), runMap(op, in).get("outputs").toString());
                List<?> quotes = (List<?>) in.get("quotes");
                for (int t = 0; t < 5; t++) {
                    int j = rnd.nextInt(quotes.size());
                    Map<?, ?> q = (Map<?, ?>) quotes.get(j);
                    if (!q.containsKey("rate")) {
                        continue;
                    }
                    @SuppressWarnings("unchecked")
                    Map<Object, Object> inputs = new LinkedHashMap<>((Map<Object, Object>) in);
                    List<Object> qs = new ArrayList<>(quotes);
                    Map<Object, Object> moved = new LinkedHashMap<>(q);
                    moved.put("rate", num(q.get("rate")) + (rnd.nextBoolean() ? 1e-4 : -1e-4));
                    qs.set(j, moved);
                    inputs.put("quotes", qs);
                    Map<?, ?> r = runMap(op, inputs);
                    if (!"ok".equals(r.get("status"))) {
                        continue;
                    }
                    List<Object[]> a = pillars(base);
                    List<Object[]> b = pillars(r);
                    int first = -1;
                    for (int k = 0; k < a.size(); k++) {
                        if (!same(a.get(k), b.get(k))) {
                            first = k;
                            break;
                        }
                    }
                    // quotes are in maturity order, one pillar per quote: a change at quote j leaves pillars
                    // 0..j-1 bit-identical and moves pillar j (K-4 on the production bootstrap)
                    assertEquals(quotes.size(), a.size());
                    assertEquals(j, first, c.get("case_id") + " quote " + j);
                    tried++;
                }
            }
        }
        assertTrue(used >= 4);
        assertTrue(tried >= 10, "tried " + tried);
        org.quantforge.risk.StageKEvidence.write("incremental_property_stage_b", "{\"stage_b_cases\": " + used
                + ", \"quote_changes_checked\": " + tried + ", \"earlier_pillars_bit_identical\": true"
                + ", \"first_changed_pillar_is_the_changed_quote\": true}");
    }

    // --- KR-8 method ---------------------------------------------------------------------------------

    private static String ladderInputs(int index) throws IOException {
        Map<?, ?> c = (Map<?, ?>) cases("stage_g/aadladder_g.json").get(index);
        StringBuilder b = new StringBuilder();
        Json.write(b, c.get("inputs"));
        return b.toString();
    }

    private static String withMethod(String inputs, String method) {
        return inputs.substring(0, inputs.length() - 1) + ",\"method\":\"" + method + "\"}";
    }

    @Test
    void k8DefaultMethodIsG18() throws IOException {
        String i = ladderInputs(0);
        String a = run("rates.shortrate.bermudan_ladder", i);
        assertEquals(a, run("rates.shortrate.bermudan_ladder", withMethod(i, "G18_IMPLICIT")));
        assertEquals("E_SCHEMA", code("rates.shortrate.bermudan_ladder", withMethod(i, "CN")));
        assertEquals("E_SCHEMA", code("rates.shortrate.bermudan_swaption", withMethod(i, "CN")));
        Map<?, ?> c = runMap("rates.shortrate.bermudan_ladder", Json.parse(withMethod(i,
                "CN_RANNACHER_SMOOTHED")).value());
        Map<?, ?> d = runMap("rates.shortrate.bermudan_swaption", Json.parse(withMethod(i,
                "CN_RANNACHER_SMOOTHED")).value());
        Map<?, ?> g = runMap("rates.shortrate.bermudan_swaption", Json.parse(i).value());
        Object cp = ((Map<?, ?>) c.get("outputs")).get("price");
        assertEquals(cp, ((Map<?, ?>) d.get("outputs")).get("price"));
        assertNotEquals(cp, ((Map<?, ?>) g.get("outputs")).get("price"));
        assertFalse(a.contains("CN_RANNACHER"));
        assertEquals(4, ((Map<?, ?>) c.get("outputs")).size());
    }
}
