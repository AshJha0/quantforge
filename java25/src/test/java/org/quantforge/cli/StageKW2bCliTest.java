package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Json;

/**
 * Replays the nine stage K wave 2b golden suites in process through the handlers of {@link OpsStageKW2b}, before the
 * coordinator registers them: the same input layer ({@link In}), the same gate order as Main.apply, and the
 * GoldenSuiteTest judge at each case's own tolerance. Case counts are read from the files, never typed here. Each
 * suite also prints the largest relative difference between this build and the golden values.
 */
class StageKW2bCliTest {
    private static final Path DIR = Path.of("..", "datasets", "golden", "stage_k");
    private static final Map<String, Function<In, Out>> TABLE = new LinkedHashMap<>();

    static {
        OpsStageKW2b.register(TABLE);
    }

    static Map<String, Object> run(String op, Map<?, ?> inputs) {
        Map<String, Object> r = new LinkedHashMap<>();
        In in = new In(inputs, !In.pageLimited(op));
        try {
            Out out;
            try {
                out = TABLE.get(op).apply(in);
                in.gate();
            } catch (org.quantforge.core.QfError e) {
                if (in.pendingLimit() != null && !e.code().equals("E_SCHEMA")) {
                    throw in.pendingLimit();
                }
                if (in.pendingDomain() != null && !e.code().equals("E_SCHEMA") && !e.code().equals("E_LIMIT")) {
                    throw in.pendingDomain();
                }
                throw e;
            }
            r.put("status", "ok");
            r.put("outputs", out.outputs());
        } catch (org.quantforge.core.QfError e) {
            r.put("status", "error");
            r.put("error", Map.of("code", e.code()));
        }
        StringBuilder b = new StringBuilder();
        Json.write(b, r);
        @SuppressWarnings("unchecked")
        Map<String, Object> back = (Map<String, Object>) Json.parse(b.toString()).value();
        return back;
    }

    /** Largest |got - expected| / |expected| over every non-zero expected number; [relative, absolute at 0]. */
    private static void diff(Object got, Object want, double[] worst) {
        if (want instanceof Map<?, ?> w && got instanceof Map<?, ?> g) {
            for (Object k : w.keySet()) {
                diff(g.get(k), w.get(k), worst);
            }
        } else if (want instanceof List<?> w && got instanceof List<?> g) {
            for (int i = 0; i < Math.min(w.size(), g.size()); i++) {
                diff(g.get(i), w.get(i), worst);
            }
        } else if (want instanceof Json.Number w && got instanceof Json.Number g) {
            double e = w.value();
            double d = Math.abs(g.value() - e);
            if (e != 0.0) {
                worst[0] = Math.max(worst[0], d / Math.abs(e));
            } else {
                worst[1] = Math.max(worst[1], d);
            }
        }
    }

    /** Replays one suite; returns {cases, value cases, error cases, two-error cases}. */
    static int[] suite(String name) throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(DIR.resolve(name + ".json"))).value();
        List<?> cases = (List<?>) doc.get("cases");
        List<String> failures = new ArrayList<>();
        Map<String, Map<?, ?>> peers = new HashMap<>();
        int values = 0;
        int errors = 0;
        int two = 0;
        double[] worst = new double[2];
        for (Object o : cases) {
            Map<?, ?> c = (Map<?, ?>) o;
            Map<String, Object> result = run((String) c.get("operation"), (Map<?, ?>) c.get("inputs"));
            peers.put(String.valueOf(c.get("case_id")), result);
            String problem = GoldenSuiteTest.judge(c, result, peers);
            if (problem != null) {
                failures.add(c.get("case_id") + ": " + problem);
            }
            Map<?, ?> expected = (Map<?, ?>) c.get("expected");
            if ("ok".equals(expected.get("status"))) {
                values++;
                diff(result.get("outputs"), expected.get("outputs"), worst);
            } else {
                errors++;
            }
            if (String.valueOf(c.get("description")).contains("two errors")) {
                two++;
            }
        }
        System.out.printf("KW2B-REPLAY %s: %d cases (%d value, %d error), max rel diff %.3e, max abs diff at 0 %.3e%n",
                name, cases.size(), values, errors, worst[0], worst[1]);
        assertTrue(failures.isEmpty(), () -> failures.size() + " failures: " + failures);
        assertTrue(!cases.isEmpty());
        return new int[] {cases.size(), values, errors, two};
    }

    @Test
    void cvaValueGoldens() throws IOException {
        for (String s : List.of("cva_k", "df_k", "sacva_k")) {
            int[] n = suite(s);
            assertEquals(n[0], n[1], s + " holds value cases only");
        }
    }

    @Test
    void leverageValueGoldens() throws IOException {
        for (String s : List.of("lev_k", "lex_k")) {
            int[] n = suite(s);
            assertEquals(n[0], n[1], s + " holds value cases only");
        }
    }

    @Test
    void errorGoldens() throws IOException {
        int two = 0;
        for (String s : List.of("cva_ke", "sacva_ke", "lev_ke", "lex_ke")) {
            int[] n = suite(s);
            assertEquals(n[0], n[2], s + " holds error cases only");
            two += n[3];
        }
        assertTrue(two >= 1, "two-error cases present");
    }

    @Test
    void registersFourVerbs() {
        assertEquals(List.of("risk.cva.ba", "risk.cva.sa", "risk.capital.leverage", "risk.capital.large_exposures"),
                new ArrayList<>(TABLE.keySet()));
        for (String op : TABLE.keySet()) {
            assertNotNull(Operations.find(op), op + " is not registered");
        }
    }

    private static Map<?, ?> parse(String json) {
        return (Map<?, ?>) Json.parse(json).value();
    }

    private static String code(Map<String, Object> r) {
        return r.get("error") == null ? "ok" : (String) ((Map<?, ?>) r.get("error")).get("code");
    }

    @Test
    void inputLayerOrder() {
        // unlisted class key: E_SCHEMA in the reader, ahead of a non-finite real
        assertEquals("E_SCHEMA", code(run("risk.cva.sa", parse("{\"reporting_currency\":\"USD\",\"m_cva\":\"NaN\","
                + "\"classes\":{\"XX.DELTA\":[]}}"))));
        // CCS.VEGA is read and refused by the core as E_INPUT
        assertEquals("E_INPUT", code(run("risk.cva.sa", parse("{\"reporting_currency\":\"USD\","
                + "\"classes\":{\"CCS.VEGA\":[]}}"))));
        // the finite rule outranks a structural E_INPUT (reporting currency not a code)
        assertEquals("E_DOMAIN", code(run("risk.cva.sa", parse("{\"reporting_currency\":\"usd\",\"m_cva\":\"Infinity\","
                + "\"classes\":{}}"))));
        // empty classes: total 0
        Map<String, Object> r = run("risk.cva.sa", parse("{\"reporting_currency\":\"USD\",\"classes\":{}}"));
        assertEquals(0.0, ((Json.Number) ((Map<?, ?>) r.get("outputs")).get("total")).value());
        // the ignored trading book fields are still read for type and finiteness (KR-131)
        assertEquals("E_SCHEMA", code(run("risk.capital.large_exposures", parse("{\"tier1\":100,\"counterparties\":"
                + "[{\"id\":\"A\"}],\"trading_book\":[{\"id\":\"p\",\"counterparty\":\"A\",\"seniority\":\"SENIOR\","
                + "\"notional\":1,\"market_value\":1,\"cash_equity\":1}]}"))));
        assertEquals("E_DOMAIN", code(run("risk.capital.large_exposures", parse("{\"tier1\":100,\"counterparties\":"
                + "[{\"id\":\"A\"}],\"trading_book\":[{\"id\":\"p\",\"counterparty\":\"B\",\"seniority\":\"SENIOR\","
                + "\"notional\":1,\"market_value\":1,\"maturity_years\":\"NaN\"}]}"))));
        // optional lists absent: leverage with on-balance items only
        r = run("risk.capital.leverage", parse("{\"tier1\":3,\"on_balance\":[100]}"));
        assertEquals(true, ((Map<?, ?>) r.get("outputs")).get("meets_minimum"));
        // the generic per-array cap (KR-126) is E_LIMIT, ahead of E_DOMAIN
        List<Object> many = new ArrayList<>();
        for (int i = 0; i < 100_001; i++) {
            many.add(new Json.Number(1.0, "1"));
        }
        Map<String, Object> big = new LinkedHashMap<>();
        big.put("tier1", new Json.Number(-1.0, "-1"));
        big.put("on_balance", many);
        assertEquals("E_LIMIT", code(run("risk.capital.leverage", big)));
    }
}
