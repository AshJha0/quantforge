package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;

/** Findings of the 2026-11-12 review that name this build or every build (repair round R6). */
class ReviewR6Test {
    private static Map<?, ?> run(String operation, String inputs) {
        String request = "{\"schema_version\":\"1.0\",\"case_id\":\"r6\",\"operation\":\"" + operation
                + "\",\"inputs\":{" + inputs + "}}";
        return (Map<?, ?>) Json.parse(Main.handle(request).json()).value();
    }

    /** Finding 15, R6-8: a finite coupon that overflows the conversion factor is E_DOMAIN, not a crash. */
    @Test
    void conversionFactorOverflowIsDomain() {
        Map<?, ?> r = run("bond.futures.conversion_factor", "\"bond\":{\"maturity\":\"2033-11-15\",\"coupon\":-1e308,"
                + "\"frequency\":2},\"delivery_month\":\"2026-12\",\"notional_coupon\":0.06");
        assertEquals("error", r.get("status"));
        assertEquals("E_DOMAIN", ((Map<?, ?>) r.get("error")).get("code"));
    }

    private static final String QUOTES = "\"as_of\":\"2026-11-06\",\"convention\":\"SOFR\",\"quotes\":["
            + "{\"tenor\":\"1W\",\"rate\":0.0387},{\"tenor\":\"1M\",\"rate\":0.0386},{\"tenor\":\"3M\",\"rate\":0.0383},"
            + "{\"tenor\":\"6M\",\"rate\":0.0377},{\"tenor\":\"1Y\",\"rate\":0.0365},{\"tenor\":\"2Y\",\"rate\":0.035},"
            + "{\"tenor\":\"3Y\",\"rate\":0.0345},{\"tenor\":\"5Y\",\"rate\":0.035},{\"tenor\":\"7Y\",\"rate\":0.036},"
            + "{\"tenor\":\"10Y\",\"rate\":0.0375},{\"tenor\":\"15Y\",\"rate\":0.039},{\"tenor\":\"20Y\",\"rate\":0.0395},"
            + "{\"tenor\":\"30Y\",\"rate\":0.0385}],\"bump_bp\":1.0,\"interpolation\":";

    private static double maxUpper(String interp) {
        Map<?, ?> r = run("risk.curve.jacobian", QUOTES + "\"" + interp + "\"");
        assertEquals("ok", r.get("status"), String.valueOf(r));
        List<?> jac = (List<?>) ((Map<?, ?>) r.get("outputs")).get("jacobian");
        double m = 0.0;
        for (int i = 0; i < jac.size(); i++) {
            List<?> row = (List<?>) jac.get(i);
            for (int j = i + 1; j < row.size(); j++) {
                m = Math.max(m, Math.abs(((Number) row.get(j)).doubleValue()));
            }
        }
        return m;
    }

    /**
     * Finding 3: this build reports the full central difference, with no upper-triangle mask. A local method has a
     * zero upper triangle; a global one (monotone convex) does not, and the entries must be reported.
     */
    @Test
    void jacobianUpperTriangleIsNotMasked() {
        assertEquals(0.0, maxUpper("LINEAR_ZERO"), 1e-12);
        assertTrue(maxUpper("MONOTONE_CONVEX") > 1e-3);
    }
}
