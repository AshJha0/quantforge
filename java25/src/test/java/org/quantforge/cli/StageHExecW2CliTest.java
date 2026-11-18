package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/** Stage H wave 2 execution through the CLI: HR-66 error order, HR-3 integer output, non-finite guard, limits. */
class StageHExecW2CliTest {
    private static String run(String op, String inputs) {
        return Main.handle("{\"schema_version\":\"1.0\",\"case_id\":\"c\",\"operation\":\"" + op
                + "\",\"inputs\":" + inputs + "}").json();
    }

    private static void code(String op, String inputs, String code) {
        String j = run(op, inputs);
        assertTrue(j.contains("\"" + code + "\""), op + " " + j);
    }

    @Test
    void unitsAreIntegers() {
        String a = run("exec.algo.arrival",
                "{\"quantity\":1001,\"n_buckets\":2,\"urgency\":0.69314718055994531,\"mode\":\"UNITS\"}");
        assertTrue(a.contains("\"slices\":[601,400]"), a);
        String p = run("exec.algo.pair", "{\"leg_a\":{\"side\":\"BUY\",\"quantity\":1000,\"price\":30},\"leg_b\":"
                + "{\"side\":\"SELL\",\"price\":70},\"pair_mode\":\"CASH_BALANCED\",\"n_buckets\":3,\"mode\":\"UNITS\"}");
        assertTrue(p.contains("\"slices_b\":[143,143,143],\"quantity_b\":429"), p);
    }

    @Test
    void errorPrecedence() {
        code("exec.algo.arrival", "{\"quantity\":10,\"n_buckets\":0,\"urgency\":-1}", "E_INPUT");
        code("exec.algo.close", "{\"quantity\":10,\"close_volume\":-1,\"auction_participation\":2,\"profile\":[]}",
                "E_INPUT");
        code("exec.algo.liquidity_seek", "{\"side\":\"BUY\",\"quantity\":10,\"limit_price\":-1,\"take_fraction\":0,"
                + "\"books\":[[[2,1],[1,1]]]}", "E_INPUT");
        code("exec.algo.liquidity_seek", "{\"side\":\"BUY\",\"quantity\":10,\"limit_price\":1,\"take_fraction\":0,"
                + "\"books\":[]}", "E_INPUT");
        code("exec.algo.pair", "{\"leg_a\":{\"side\":\"BUY\",\"quantity\":10,\"price\":-1},\"leg_b\":{\"side\":\"BUY\","
                + "\"price\":1},\"pair_mode\":\"CASH_BALANCED\",\"n_buckets\":2}", "E_INPUT");
        code("exec.algo.basket", "{\"legs\":[{\"side\":\"BUY\",\"quantity\":0,\"price\":-1}],\"n_buckets\":2}",
                "E_INPUT");
        code("exec.tca.attribution", "{\"side\":\"BUY\",\"decision_price\":-1,\"arrival_mid\":1,\"end_price\":1,"
                + "\"order_quantity\":1,\"fills\":[{\"quantity\":2,\"price\":1,\"mid\":1}],\"fees\":0}", "E_INPUT");
        String prm = "\"params\":{\"a1\":1,\"a2\":1,\"a3\":1,\"a4\":1,\"b1\":1}";
        code("exec.tca.pretrade", "{\"quantity\":0,\"adv\":-1,\"daily_vol\":0.1,\"participation\":0.5,"
                + "\"half_spread_bps\":0," + prm + "}", "E_INPUT");
        code("exec.algo.pair", "{\"leg_a\":{\"side\":\"BUY\",\"quantity\":0,\"price\":1},\"leg_b\":{\"side\":\"SELL\","
                + "\"price\":1},\"pair_mode\":\"OTHER\",\"n_buckets\":2}", "E_SCHEMA");
        code("exec.algo.liquidity_seek", "{\"side\":\"BUY\",\"quantity\":10,\"limit_price\":1,\"take_fraction\":1,"
                + "\"books\":[[[1,1,1]]]}", "E_SCHEMA");
        code("exec.algo.arrival", "{\"quantity\":10,\"n_buckets\":2,\"urgency\":0,\"mode\":\"LOTS\"}", "E_SCHEMA");
        code("exec.algo.close", "{\"quantity\":10,\"close_volume\":-1,\"auction_participation\":0.5,\"profile\":[1]}",
                "E_DOMAIN");
        code("exec.algo.liquidity_seek", "{\"side\":\"SELL\",\"quantity\":10,\"limit_price\":1,\"take_fraction\":1,"
                + "\"books\":[[[2,1],[-1,1]]]}", "E_DOMAIN");
        code("exec.tca.pretrade", "{\"quantity\":1,\"adv\":1,\"daily_vol\":0,\"participation\":0.5,"
                + "\"half_spread_bps\":0,\"params\":{\"a1\":1,\"a2\":1,\"a3\":0,\"a4\":1,\"b1\":1}}", "E_DOMAIN");
        code("exec.algo.pair", "{\"leg_a\":{\"side\":\"BUY\",\"quantity\":10,\"price\":1},\"leg_b\":{\"side\":\"SELL\","
                + "\"price\":1},\"pair_mode\":\"HEDGED\",\"n_buckets\":2}", "E_INPUT");
        code("exec.algo.arrival", "{\"quantity\":10,\"n_buckets\":100001,\"urgency\":0}", "E_LIMIT");
        code("exec.algo.arrival", "{\"quantity\":10,\"n_buckets\":2,\"urgency\":\"NaN\"}", "E_DOMAIN");
        code("exec.algo.liquidity_seek", "{\"side\":\"BUY\",\"quantity\":10,\"limit_price\":1,\"take_fraction\":1,"
                + "\"books\":[[[\"Infinity\",1]]]}", "E_DOMAIN");
    }
}
