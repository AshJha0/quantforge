package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;

/** Stage I rulings checked at the CLI layer: I-41 fixed key sets, I-42 unknown targets, I-47 nulls, I-50 fills. */
class StageIRulingsTest {

    private static String code(String operation, String inputs) {
        String request = "{\"schema_version\":\"1.0\",\"case_id\":\"t\",\"operation\":\"" + operation
                + "\",\"inputs\":" + inputs + "}";
        Map<?, ?> r = (Map<?, ?>) Json.parse(Main.handle(request).json()).value();
        return "ok".equals(r.get("status")) ? "ok" : String.valueOf(((Map<?, ?>) r.get("error")).get("code"));
    }

    private static final String MARKET = "\"spot\":100,\"rate\":0.03,\"dividend_yield\":0.01,\"volatility\":0.2,";
    private static final String BOOK = "\"portfolio\":[{\"instrument\":\"CALL\",\"strike\":100,\"expiry_years\":1,"
            + "\"quantity\":-10}],";

    @Test
    void greekInstrumentsHaveFixedKeySets() {
        String ok = "{" + MARKET + BOOK + "\"hedges\":[{\"instrument\":\"UNDERLYING\"}],\"targets\":[\"DELTA\"]}";
        assertEquals("ok", code("hedge.greeks.neutralise", ok));
        assertEquals("E_INPUT", code("hedge.greeks.neutralise", "{" + MARKET + BOOK
                + "\"hedges\":[{\"instrument\":\"UNDERLYING\",\"quantity\":5}],\"targets\":[\"DELTA\"]}"));
        assertEquals("E_INPUT", code("hedge.greeks.neutralise", "{" + MARKET
                + "\"portfolio\":[{\"instrument\":\"UNDERLYING\"}],"
                + "\"hedges\":[{\"instrument\":\"UNDERLYING\"}],\"targets\":[\"DELTA\"]}"));
        assertEquals("E_INPUT", code("hedge.greeks.neutralise", "{" + MARKET + BOOK
                + "\"hedges\":[{\"instrument\":\"UNDERLYING\",\"colour\":1}],\"targets\":[\"DELTA\"]}"));
        assertEquals("E_SCHEMA", code("hedge.greeks.neutralise", "{" + MARKET + BOOK
                + "\"hedges\":[{\"instrument\":\"UNDERLYING\"}],\"targets\":[\"THETA\"]}"));
    }

    @Test
    void nullOptionalKeysAreSchemaErrors() {
        assertEquals("E_SCHEMA", code("hedge.qp.solve", "{\"a\":[[1]],\"b\":[1],\"weights\":[1],\"ridge\":null}"));
        assertEquals("ok", code("hedge.qp.solve", "{\"a\":[[1]],\"b\":[1],\"weights\":[1],\"lower\":[null]}"));
    }

    @Test
    void oneOrdersFillsKeepTheGeneralArrayLimit() {
        StringBuilder fills = new StringBuilder();
        for (int i = 0; i < 100_001; i++) {
            fills.append(i == 0 ? "" : ",").append("{\"quantity\":1,\"price\":100}");
        }
        assertEquals("E_LIMIT", code("hedge.slippage.report", "{\"orders\":[{\"quantity\":200000,"
                + "\"decision_price\":100,\"final_price\":100,\"half_spread\":0,\"impact\":0,\"fills\":[" + fills
                + "]}]}"));
    }
}
