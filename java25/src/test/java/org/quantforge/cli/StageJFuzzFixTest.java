package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;

/** Stage J lane J-0b: rulings J-0b.1 (horizon limit), J-0b.2 (overflowing squared return), J-0b.3 (ragged rows). */
class StageJFuzzFixTest {

    private static String code(String operation, String inputs) {
        String request = "{\"schema_version\":\"1.0\",\"case_id\":\"t\",\"operation\":\"" + operation
                + "\",\"inputs\":" + inputs + "}";
        Map<?, ?> r = (Map<?, ?>) Json.parse(Main.handle(request).json()).value();
        return "ok".equals(r.get("status")) ? "ok" : String.valueOf(((Map<?, ?>) r.get("error")).get("code"));
    }

    @Test
    void rulingsJ0b() {
        assertEquals("E_LIMIT", code("vol.garch.forecast", "{\"omega\":5e-06,\"alpha\":0.12,\"beta\":0.82,\"next_variance\":0.0003,\"horizon\":100001,\"periods_per_year\":252.0}"));
        assertEquals("E_LIMIT", code("vol.garch.forecast", "{\"omega\":5e-06,\"alpha\":0.12,\"beta\":0.82,\"next_variance\":0.0003,\"horizon\":2147483648,\"periods_per_year\":252.0}"));
        assertEquals("E_NON_FINITE", code("vol.garch.estimate", "{\"returns\":[0.01,-0.012,0.01,-0.012,0.01,-2.6755826e+297,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012],\"initial_variance\":1e-4,\"distribution\":\"NORMAL\",\"demean\":true}"));
        assertEquals("E_INPUT", code("exotic.basket.moment", "{\"forwards\":[100.0,100.0],\"weights\":[0.5,0.5],\"vols\":[0.2,0.2],\"correlation\":[[1.0,1.0],[]],\"strike\":100.0,\"expiry_years\":1.0,\"rate\":0.03,\"option_type\":\"CALL\"}"));
        assertEquals("E_INPUT", code("exotic.basket.moment", "{\"forwards\":[100.0,100.0],\"weights\":[0.5,0.5],\"vols\":[0.2,0.2],\"correlation\":[[1.0],[0.0,1.0]],\"strike\":100.0,\"expiry_years\":1.0,\"rate\":0.03,\"option_type\":\"CALL\"}"));
        assertEquals("E_INPUT", code("exotic.basket.moment", "{\"forwards\":[100.0,100.0],\"weights\":[0.5,0.5],\"vols\":[0.2,0.2],\"correlation\":[[1.0,0.0],[0.0,1.0,0.0]],\"strike\":100.0,\"expiry_years\":1.0,\"rate\":0.03,\"option_type\":\"CALL\"}"));
        assertEquals("ok", code("vol.garch.forecast", "{\"omega\":5e-06,\"alpha\":0.12,\"beta\":0.82,\"next_variance\":0.0003,\"horizon\":100000,\"periods_per_year\":252.0}"));
    }
}
