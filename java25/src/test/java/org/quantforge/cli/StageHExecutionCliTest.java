package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collections;
import org.junit.jupiter.api.Test;

/** Stage H wave 1 operations through the CLI entry point: wiring, HR-3 integer output, HR-9 limits, HR-10 label. */
class StageHExecutionCliTest {
    private static String run(String op, String inputs) {
        return Main.handle("{\"schema_version\":\"1.0\",\"case_id\":\"c\",\"operation\":\"" + op
                + "\",\"inputs\":" + inputs + "}").json();
    }

    private static void has(String json, String part) {
        assertTrue(json.contains(part), json);
    }

    private static final String AC = "\"quantity\":1e6,\"horizon\":5,\"n_steps\":5,\"sigma\":0.95,\"epsilon\":0.0625,"
            + "\"eta\":2.5e-6,\"gamma\":2.5e-7";

    @Test
    void everyOperationAnswers() {
        has(run("exec.schedule.twap", "{\"quantity\":1000,\"n_buckets\":3,\"mode\":\"UNITS\"}"),
                "\"slices\":[334,333,333]");
        has(run("exec.schedule.vwap", "{\"quantity\":10,\"profile\":[1,1,1],\"mode\":\"UNITS\"}"), "[4,3,3]");
        has(run("exec.schedule.pov", "{\"quantity\":1000,\"participation\":0.2,\"market_volume\":[1000,2000,4000],"
                + "\"mode\":\"UNITS\"}"), "\"slices\":[250,500,250],\"filled\":1000,\"residual\":0");
        has(run("exec.ac.trajectory", "{" + AC + ",\"risk_aversion\":0}"), "\"expected_cost\":662500");
        has(run("exec.ac.frontier", "{" + AC + ",\"risk_aversions\":[0,1e-6]}"), "\"variances\":[");
        has(run("exec.impact.sqrt", "{\"quantity\":1e5,\"daily_volume\":1e7,\"daily_vol\":0.02}"),
                "\"model\":\"assumed parameters; not calibrated to any venue\"");
        has(run("exec.impact.ow_optimal", "{\"quantity\":1000,\"horizon\":1,\"resilience\":8}"), "\"rate\":800");
        String tca = "{\"side\":\"BUY\",\"decision_price\":100,\"arrival_price\":100.10,\"end_price\":101,"
                + "\"order_quantity\":1000,\"fills\":[{\"quantity\":600,\"price\":100.20},{\"quantity\":200,"
                + "\"price\":100.30}],\"fees\":5";
        String a = run("exec.tca.shortfall", tca + "}");
        has(a, "\"total_bps\"");
        assertTrue(!a.contains("vwap_slippage"), a);
        has(run("exec.tca.shortfall", tca + ",\"benchmark_vwap\":100.2}"), "\"vwap_slippage\"");
        has(run("micro.mm.as_quotes", "{\"mid\":100,\"inventory\":2,\"risk_aversion\":0.1,\"sigma\":2,"
                + "\"time_left\":1,\"k\":1.5}"), "\"reservation\":99.2");
    }

    @Test
    void errorOrderAndLimits() {
        has(run("exec.schedule.twap", "{\"quantity\":1000,\"n_buckets\":100001,\"mode\":\"UNITS\"}"), "E_LIMIT");
        has(run("exec.schedule.twap", "{\"quantity\":1000,\"n_buckets\":100001,\"mode\":\"BAD\"}"), "E_SCHEMA");
        has(run("exec.ac.trajectory", "{" + AC.replace("\"n_steps\":5", "\"n_steps\":100001")
                + ",\"risk_aversion\":0}"), "E_LIMIT");
        has(run("exec.schedule.pov", "{\"quantity\":1000,\"participation\":\"NaN\",\"market_volume\":[1],"
                + "\"mode\":\"UNITS\"}"), "E_DOMAIN");
        String fill = "{\"quantity\":1,\"price\":100}";
        String many = String.join(",", Collections.nCopies(100_001, fill));
        String tca = "{\"side\":\"BUY\",\"decision_price\":100,\"arrival_price\":100,\"end_price\":100,"
                + "\"order_quantity\":2e6,\"fees\":0,\"fills\":[";
        has(run("exec.tca.shortfall", tca + many + "]}"), "\"status\":\"ok\""); // HR-9: fills limit is 1,000,000
        has(run("exec.tca.shortfall", tca + many + "],\"side\":\"HOLD\"}"), "E_PARSE");
    }
}
