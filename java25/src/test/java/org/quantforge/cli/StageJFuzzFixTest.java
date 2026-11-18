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

    /** J-W3-18 to J-W3-20: fuzz run 43858847696 (seed 4). */
    @Test
    void rulingsJw3Seed4() {
        assertEquals("E_NON_FINITE", code("hedge.integer.solve", "{\"a\":[[1.0,9.5e+299],[0.95,1.0]],\"b\":[-1.265,-1.27],\"weights\":[1.0,1.0],\"lot_sizes\":[1.0,1.0]}"));
        assertEquals("E_NON_FINITE", code("rates.shortrate.capfloor", "{\"model\":\"CIR\",\"mean_reversion\":0.25,\"long_term_mean\":0.04,\"sigma\":0.08,\"short_rate\":0.03,\"period_times\":[5e-324,2.0,3.0,4.0,5.0,6.0,7.0],\"strike\":0.03,\"cap_floor\":\"CAP\",\"notional\":1000000.0}"));
        assertEquals("E_NON_FINITE", code("rates.shortrate.capfloor", "{\"model\":\"CIR\",\"mean_reversion\":0.25,\"long_term_mean\":0.04,\"sigma\":0.08,\"short_rate\":0.03,\"period_times\":[1e-200,2.0,3.0,4.0,5.0,6.0,7.0],\"strike\":0.03,\"cap_floor\":\"CAP\",\"notional\":1000000.0}"));
        String request = "{\"schema_version\":\"1.0\",\"case_id\":\"t\",\"operation\":"
                + "\"research.portfolio.mean_variance\",\"inputs\":"
                + "{\"expected_returns\":[0.06771,0.098313,0.028432,0.05484,0.045746,0.009556,0.108223,0.055019],\"covariance\":[[0.048331,0.004555,-0.017935,0.016324,-0.006755,0.004188,0.012427,-0.006854],[0.004555,0.032681,-0.003512,-0.000217,-0.010136,0.022911,0.013417,-0.001925],[-0.017935,-0.003512,0.034533,-0.005937,0.014412,-0.007383,-0.004539,0.001099],[0.016324,-0.000217,-0.005937,0.036879,0.00083,-0.002874,-0.011025,-0.005214],[-0.006755,-0.010136,0.014412,0.00083,0.042148,-0.007134,-0.006968,-0.002897],[0.004188,0.022911,-0.007383,-0.002874,-0.007134,0.045017,0.009949,0.000445],[0.012427,0.013417,-0.004539,-0.011025,-0.006968,0.009949,0.055737,-0.002087],[-0.006854,-0.001925,0.001099,-0.005214,-0.002897,0.000445,-0.002087,0.030976]],\"risk_aversion\":3.0,\"lower\":[-9007199254740992.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0],\"upper\":[0.2375,0.2375,0.2375,0.2375,0.2375,0.2375,0.2375,0.2375]}}";
        Map<?, ?> r = (Map<?, ?>) Json.parse(Main.handle(request).json()).value();
        assertEquals("ok", r.get("status"));
        java.util.List<?> w = (java.util.List<?>) ((Map<?, ?>) r.get("outputs")).get("weights");
        double sum = 0;
        for (Object v : w) {
            sum += ((Json.Number) v).value();
        }
        assertEquals(1.0, sum, 1e-12);
        assertEquals(0.062395242276264584, ((Json.Number) w.get(0)).value(), 1e-12);
    }

    /** J-W3-21: CIR at t_0 = 1e-10 (noncentrality about 1.9e11); C++ gave 3690.6 for the first caplet. */
    @Test
    void rulingJw321TinyFirstTime() {
        String cap = "{\"model\":\"CIR\",\"mean_reversion\":0.25,\"long_term_mean\":0.04,\"sigma\":0.08,\"short_rate\":0.03,"
                + "\"period_times\":[1e-10,2.0,3.0,4.0,5.0,6.0,7.0],\"strike\":0.03,\"cap_floor\":\"CAP\",\"notional\":1000000.0}";
        assertEquals(5790.068868782696, firstCaplet(cap), 5790.068868782696 * 1e-12);
        assertEquals(0.0, firstCaplet(cap.replace("\"CAP\"", "\"FLOOR\"")));
        String near = cap.replace("\"short_rate\":0.03", "\"short_rate\":0.0263").replace("1e-10", "1e-06");
        assertEquals("E_LIMIT", code("rates.shortrate.capfloor", near));
    }

    private static double firstCaplet(String inputs) {
        String request = "{\"schema_version\":\"1.0\",\"case_id\":\"t\",\"operation\":\"rates.shortrate.capfloor\",\"inputs\":"
                + inputs + "}";
        Map<?, ?> r = (Map<?, ?>) Json.parse(Main.handle(request).json()).value();
        assertEquals("ok", r.get("status"));
        java.util.List<?> c = (java.util.List<?>) ((Map<?, ?>) r.get("outputs")).get("caplet_prices");
        return ((Json.Number) c.get(0)).value();
    }
}
