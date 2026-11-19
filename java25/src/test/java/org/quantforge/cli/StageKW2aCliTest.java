package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;

/**
 * Replays every case of the two stage K wave 2 lane A golden suites (drc_k for K-8a, ima_k for K-8f) in process
 * through the handlers of {@link OpsStageKW2a}, before the coordinator registers them: the same input layer
 * ({@link In}), the same gate order as Main.apply, and the GoldenSuiteTest judge at each case's tolerance. Case
 * counts are read from the files, never hard-coded.
 */
class StageKW2aCliTest {
    private static final Path DIR = Path.of("..", "datasets", "golden", "stage_k");
    private static final Map<String, Function<In, Out>> TABLE = new LinkedHashMap<>();

    static {
        OpsStageKW2a.register(TABLE);
    }

    /** In.pageLimited with the registration line of program/STAGE_K_W2A_JAVA_HANDOVER.md applied. */
    static boolean pageLimited(String op) {
        return In.pageLimited(op) || OpsStageKW2a.PAGE_LIMITED.contains(op);
    }

    /** Main.handle without the envelope: inputs, apply with the held E_LIMIT and finite rule, then the reply. */
    static Map<String, Object> run(String op, Map<?, ?> inputs) {
        Map<String, Object> r = new LinkedHashMap<>();
        In in = new In(inputs, !pageLimited(op));
        try {
            Out out;
            try {
                out = TABLE.get(op).apply(in);
                in.gate();
            } catch (QfError e) {
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
        } catch (QfError e) {
            r.put("status", "error");
            r.put("error", Map.of("code", e.code()));
        }
        StringBuilder b = new StringBuilder();
        Json.write(b, r);
        @SuppressWarnings("unchecked")
        Map<String, Object> back = (Map<String, Object>) Json.parse(b.toString()).value();
        return back;
    }

    /** Largest relative difference |x - e| / |e| over the nonzero expected numbers; absolute where e = 0. */
    private static void diff(Object got, Object want, double[] worst) {
        if (want instanceof Map<?, ?> m) {
            for (Object k : m.keySet()) {
                diff(((Map<?, ?>) got).get(k), m.get(k), worst);
            }
        } else if (want instanceof List<?> l) {
            for (int i = 0; i < l.size(); i++) {
                diff(((List<?>) got).get(i), l.get(i), worst);
            }
        } else if (want instanceof Json.Number e && got instanceof Json.Number x) {
            double d = Math.abs(x.value() - e.value());
            if (e.value() != 0) {
                worst[0] = Math.max(worst[0], d / Math.abs(e.value()));
            } else {
                worst[1] = Math.max(worst[1], d);
            }
        }
    }

    /** Replays one suite; returns {cases, value cases, error cases, two-error cases, E1 cases}. */
    private static int[] suite(String name) throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(DIR.resolve(name + ".json"))).value();
        List<?> cases = (List<?>) doc.get("cases");
        List<String> failures = new ArrayList<>();
        Map<String, Map<?, ?>> peers = new HashMap<>();
        int[] counts = new int[5];
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
            String description = String.valueOf(c.get("description"));
            counts[0]++;
            if ("ok".equals(expected.get("status"))) {
                counts[1]++;
                if ("ok".equals(result.get("status"))) {
                    diff(result.get("outputs"), expected.get("outputs"), worst);
                }
            } else {
                counts[2]++;
            }
            counts[3] += description.contains("two errors") ? 1 : 0;
            counts[4] += description.contains("E1") ? 1 : 0;
        }
        System.out.printf("%s: %d cases (%d value, %d error, %d two-error, %d E1); largest relative difference %.3e,"
                + " largest absolute difference at an expected 0 %.3e%n", name, counts[0], counts[1], counts[2],
                counts[3], counts[4], worst[0], worst[1]);
        assertTrue(failures.isEmpty(), () -> failures.size() + " failures: " + failures);
        assertEquals(cases.size(), counts[1] + counts[2]);
        return counts;
    }

    @Test
    void drcGoldens() throws IOException {
        int[] c = suite("drc_k");
        assertTrue(c[1] >= 1 && c[3] >= 1 && c[4] >= 1);
    }

    @Test
    void imaGoldens() throws IOException {
        int[] c = suite("ima_k");
        assertTrue(c[1] >= 1 && c[3] >= 1 && c[4] >= 1);
    }

    @Test
    void registersFourteenVerbsNotYetInOperations() {
        assertEquals(14, TABLE.size());
        for (String op : TABLE.keySet()) {
            assertTrue(op.startsWith("risk.frtb."), op);
            // remove this check at integration, when OpsStageKW2a is added to Operations.MODULES
            assertNull(Operations.find(op), op + " is already registered");
        }
    }

    private static Json.Number num(long v) {
        return new Json.Number(v, Long.toString(v));
    }

    private static Map<?, ?> parse(String json) {
        return (Map<?, ?>) Json.parse(json).value();
    }

    private static String code(Map<String, Object> r) {
        return "ok".equals(r.get("status")) ? "ok" : (String) ((Map<?, ?>) r.get("error")).get("code");
    }

    @Test
    void limitsBeforeFiniteRuleAndStructure() {
        // KR-67: a P&L list above 1,000,000 points is E_LIMIT ahead of a NaN and of unequal lengths
        List<Object> big = new ArrayList<>(Collections.nCopies(FrtbLimit.PNL + 1, (Object) num(0)));
        big.set(0, "NaN");
        Map<String, Object> inputs = new LinkedHashMap<>();
        inputs.put("hpl", big);
        inputs.put("rtpl", List.of(num(1)));
        assertEquals("E_LIMIT", code(run("risk.frtb.pla", inputs)));
        // a P&L list above the generic 100,000 cap is accepted for es_lh (KR-67)
        List<Object> pnl = new ArrayList<>();
        for (int k = 0; k < 150_000; k++) {
            pnl.add(num(-k));
        }
        Map<String, Object> es = new LinkedHashMap<>();
        es.put("pnl", List.of(pnl, List.of(), List.of(), List.of(), List.of()));
        Map<String, Object> r = run("risk.frtb.ima.es_lh", es);
        assertEquals("ok", r.get("status"));
        assertTrue(((Json.Number) ((Map<?, ?>) r.get("outputs")).get("es")).value() > 0);
        // es_lh caps: es_t and sigma above 100,000 entries, a pnl row above 1,000,000 points
        List<Object> many = new ArrayList<>(Collections.nCopies(FrtbLimit.LIST + 1, (Object) num(0)));
        assertEquals("E_LIMIT", code(run("risk.frtb.ima.es_lh", Map.of("es_t", many))));
        assertEquals("E_LIMIT", code(run("risk.frtb.ima.es_lh", Map.of("sigma", many))));
        List<Object> rows = new ArrayList<>(Collections.nCopies(FrtbLimit.LIST + 1, (Object) List.of()));
        assertEquals("E_LIMIT", code(run("risk.frtb.ima.es_lh", Map.of("pnl", rows))));
        List<Object> longRow = new ArrayList<>(Collections.nCopies(FrtbLimit.PNL + 1, (Object) num(0)));
        assertEquals("E_LIMIT", code(run("risk.frtb.ima.es_lh", Map.of("pnl", List.of(longRow)))));
        // the other verbs keep the generic 100,000 cap
        assertEquals("E_LIMIT", code(run("risk.frtb.ima.ses", Map.of("idio_credit", many, "idio_equity", List.of(),
                "other", List.of()))));
    }

    /** The KR-67 sizes, here so the test reads like the Python limits hook. */
    private static final class FrtbLimit {
        static final int PNL = 1_000_000;
        static final int LIST = 100_000;
    }

    @Test
    void inputLayerDetails() {
        // optional booleans and lgd_applies false; the ratings map holds an unused obligor
        Map<String, Object> r = run("risk.frtb.drc_nonsec", parse("{\"positions\":[{\"id\":\"a\",\"obligor\":\"X\","
                + "\"bucket\":\"SOVEREIGN\",\"seniority\":\"EQUITY\",\"notional\":10,\"market_value\":10,"
                + "\"maturity_years\":0.25,\"cash_equity\":true,\"lgd_applies\":false}],\"ratings\":{\"X\":\"AA\","
                + "\"Y\":\"B\"}}"));
        assertEquals("ok", r.get("status"));
        // ctp positions mode with no position: hbr_ctp null, drc 0
        r = run("risk.frtb.drc_ctp", parse("{\"positions\":[]}"));
        assertNull(((Map<?, ?>) r.get("outputs")).get("hbr_ctp"));
        // imcc: an unlisted class key is E_SCHEMA before a domain error in the portfolio
        r = run("risk.frtb.ima.imcc", parse("{\"portfolio\":{\"es_rs\":1,\"es_fc\":1,\"es_rc\":0},"
                + "\"classes\":{\"RATES\":{\"es_rs\":1,\"es_fc\":1,\"es_rc\":1}}}"));
        assertEquals("E_SCHEMA", code(r));
        // lh: constituents and maturity read; n not an integer is E_SCHEMA
        r = run("risk.frtb.ima.lh", parse("{\"constituents\":[{\"weight\":1,\"n\":120}],\"maturity_days\":1}"));
        assertEquals("index+maturity", ((Map<?, ?>) r.get("outputs")).get("rule"));
        r = run("risk.frtb.ima.lh", parse("{\"constituents\":[{\"weight\":1,\"n\":1.5}]}"));
        assertEquals("E_SCHEMA", code(r));
        // rfet with no window inside the year: null window fields
        r = run("risk.frtb.rfet", parse("{\"as_of\":\"2026-06-30\",\"observations\":[\"2026-06-30\",\"2026-06-30\"]}"));
        Map<?, ?> out = (Map<?, ?>) r.get("outputs");
        assertEquals(1L, (long) ((Json.Number) out.get("distinct_days")).value());
        // capital with the qualitative add-on read
        r = run("risk.frtb.ima.capital", parse("{\"imcc_prev\":10,\"ses_prev\":0,\"imcc_avg\":10,\"ses_avg\":0,"
                + "\"exceptions\":12,\"drc\":0,\"desks\":[],\"c_u\":0,\"sa_all\":100,\"qualitative_addon\":0.25}"));
        assertEquals(45.0, ((Json.Number) ((Map<?, ?>) r.get("outputs")).get("acr_total")).value());
        assertThrows(QfError.class, () -> OpsStageKW2a.choice(new In(parse("{\"k\":\"Z\"}")), "k", List.of("A")));
    }
}
