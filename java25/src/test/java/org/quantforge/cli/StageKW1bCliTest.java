package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
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
import org.quantforge.core.QfError;

/**
 * Replays the three stage K wave 1b golden suites in process through the handlers of {@link OpsStageKW1b}, before
 * the coordinator registers them: the same input layer ({@link In}), the same gate order as Main.apply, and the
 * GoldenSuiteTest judge. tlk_k uses the already registered risk.backtest.traffic_light.
 */
class StageKW1bCliTest {
    private static final Path DIR = Path.of("..", "datasets", "golden", "stage_k");
    private static final Map<String, Function<In, Out>> TABLE = new LinkedHashMap<>();

    static {
        OpsStageKW1b.register(TABLE);
    }

    private static Function<In, Out> find(String op) {
        Function<In, Out> f = TABLE.get(op);
        return f != null ? f : Operations.find(op);
    }

    /** Main.handle without the envelope: inputs, apply with the held E_LIMIT and finite rule, then the reply. */
    static Map<String, Object> run(String op, Map<?, ?> inputs) {
        Map<String, Object> r = new LinkedHashMap<>();
        In in = new In(inputs, !In.pageLimited(op));
        try {
            Out out;
            try {
                out = find(op).apply(in);
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

    private static int suite(String name) throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(DIR.resolve(name + ".json"))).value();
        List<?> cases = (List<?>) doc.get("cases");
        List<String> failures = new ArrayList<>();
        Map<String, Map<?, ?>> peers = new HashMap<>();
        int twoErrors = 0;
        for (Object o : cases) {
            Map<?, ?> c = (Map<?, ?>) o;
            Map<String, Object> result = run((String) c.get("operation"), (Map<?, ?>) c.get("inputs"));
            peers.put(String.valueOf(c.get("case_id")), result);
            String problem = GoldenSuiteTest.judge(c, result, peers);
            if (problem != null) {
                failures.add(c.get("case_id") + ": " + problem);
            }
            if (String.valueOf(c.get("description")).contains("two errors")) {
                twoErrors++;
            }
        }
        assertTrue(failures.isEmpty(), () -> failures.size() + " failures: " + failures);
        assertTrue(!cases.isEmpty());
        return twoErrors;
    }

    @Test
    void saccrGoldens() throws IOException {
        assertTrue(suite("saccr_k") >= 1);
    }

    @Test
    void backtestGoldens() throws IOException {
        assertTrue(suite("btk_k") >= 1);
    }

    @Test
    void trafficLightOutsideCheck() throws IOException {
        suite("tlk_k");
    }

    @Test
    void registersFourVerbsAndNoCollision() {
        assertEquals(List.of("risk.saccr.ead", "risk.frtb.backtest.zone", "risk.frtb.backtest.desk",
                "risk.frtb.backtest.count"), new ArrayList<>(TABLE.keySet()));
        for (String op : TABLE.keySet()) {
            assertEquals(null, Operations.find(op), op + " already registered: drop it from this test at integration");
        }
    }

    private static Map<?, ?> parse(String json) {
        return (Map<?, ?>) Json.parse(json).value();
    }

    @Test
    void inputLayerOrderAndDefaults() {
        // enum value outside the list is E_SCHEMA, before an E_DOMAIN in the same trade
        Map<String, Object> r = run("risk.saccr.ead", parse("{\"trades\":[{\"id\":\"a\",\"asset_class\":\"FX\","
                + "\"notional\":0,\"market_value\":0,\"maturity\":1,\"position\":\"LONG\",\"hedging_set\":\"X\","
                + "\"kind\":\"SWAP\"}]}"));
        assertEquals("E_SCHEMA", ((Map<?, ?>) r.get("error")).get("code"));
        // the finite rule (E_DOMAIN) outranks a structural E_INPUT
        r = run("risk.saccr.ead", parse("{\"trades\":[{\"id\":\"a\",\"asset_class\":\"FX\",\"notional\":\"NaN\","
                + "\"market_value\":0,\"maturity\":1,\"position\":\"LONG\"}]}"));
        assertEquals("E_DOMAIN", ((Map<?, ?>) r.get("error")).get("code"));
        // margin with every optional key, option and CDO fields read
        r = run("risk.saccr.ead", parse("{\"collateral\":1,\"ir_offset\":false,\"margin\":{\"threshold\":0,\"mta\":0,"
                + "\"nica\":0,\"remargin_days\":1,\"mpor_days\":12,\"illiquid\":false,\"disputes\":false},"
                + "\"trades\":[{\"id\":\"o\",\"asset_class\":\"EQUITY\",\"notional\":10,\"market_value\":1,"
                + "\"maturity\":1,\"position\":\"SOLD\",\"kind\":\"OPTION\",\"option_type\":\"PUT\","
                + "\"underlying_price\":1,\"strike\":1,\"exercise\":1,\"shift\":0.5,\"entity\":\"E\","
                + "\"subclass\":\"INDEX\",\"treatment\":\"NORMAL\"},{\"id\":\"c\",\"asset_class\":\"CREDIT\","
                + "\"notional\":10,\"market_value\":0,\"maturity\":1,\"position\":\"BOUGHT\",\"kind\":\"CDO\","
                + "\"attachment\":0.1,\"detachment\":0.2,\"start\":0,\"end\":1,\"entity\":\"T\",\"subclass\":\"SG\"}]}"));
        assertEquals("ok", r.get("status"));
        assertEquals(12L, (long) ((Json.Number) ((Map<?, ?>) r.get("outputs")).get("mpor_days")).value());
        // the observations cap is E_LIMIT ahead of a domain error, also for the desk verb
        r = run("risk.frtb.backtest.desk", parse("{\"observations\":1000001,\"exceptions_99_actual\":-1,"
                + "\"exceptions_99_hypothetical\":0,\"exceptions_975_actual\":0,\"exceptions_975_hypothetical\":0}"));
        assertEquals("E_LIMIT", ((Map<?, ?>) r.get("error")).get("code"));
        assertThrows(QfError.class, () -> OpsStageKW1b.choice(new In(parse("{\"k\":\"Z\"}")), "k", List.of("A")));
    }
}
