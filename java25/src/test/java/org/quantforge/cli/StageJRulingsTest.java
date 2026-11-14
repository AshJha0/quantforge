package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collections;
import org.junit.jupiter.api.Test;

/** Rulings J-20 to J-22 (specifications/stage-j-rulings-w1.md) through the CLI entry point. */
class StageJRulingsTest {
    private static String run(String op, String inputs) {
        return Main.handle("{\"schema_version\":\"1.0\",\"case_id\":\"c\",\"operation\":\"" + op
                + "\",\"inputs\":" + inputs + "}").json();
    }

    private static String repeat(String item, int n) {
        return String.join(",", Collections.nCopies(n, item));
    }

    private static String backtest(int n) {
        return run("research.backtest.run",
                "{\"prices\":[" + repeat("100.0", n) + "],\"targets\":[" + repeat("0.0", n) + "]}");
    }

    @Test
    void j20PageLimitReplacesGeneralArrayLimit() {
        assertTrue(backtest(100_001).contains("\"status\":\"ok\""));
        assertTrue(backtest(1_000_001).contains("\"code\":\"E_LIMIT\""));
    }

    @Test
    void j20PboRowsJudgedByCellCap() {
        String r = run("research.stats.pbo",
                "{\"performance\":[" + repeat("[0.0,1.0]", 100_002) + "],\"n_partitions\":2}");
        assertFalse(r.contains("E_LIMIT"), r);
    }

    @Test
    void j21PowerArgumentsOutsideUnitIntervalAreDomain() {
        for (String[] ap : new String[][] {{"0.0", "0.8"}, {"-0.1", "0.8"}, {"0.05", "1.0"}, {"0.05", "1.5"}}) {
            String r = run("research.stats.power", "{\"years\":5.0,\"alpha\":" + ap[0] + ",\"power\":" + ap[1] + "}");
            assertTrue(r.contains("\"code\":\"E_DOMAIN\""), r);
        }
    }

    @Test
    void j22EmptyViterbiInputIsInputError() {
        String base = "\"initial\":[0.5,0.5],\"transition\":[[0.9,0.1],[0.1,0.9]]";
        assertTrue(run("research.regime.viterbi", "{" + base + ",\"emission\":[]}").contains("\"code\":\"E_INPUT\""));
        String g = "{" + base + ",\"observations\":[],\"means\":[0.0,1.0],\"sds\":[1.0,1.0]}";
        assertTrue(run("research.regime.viterbi", g).contains("\"code\":\"E_INPUT\""));
    }
}
