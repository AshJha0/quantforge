package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;

/** FRTB IMA backtesting (K-8e): MAR99 Table 2, the shared table, zone boundaries, desk limits, counting, errors. */
class FrtbBacktestTest {
    private static Map<?, ?> tables() throws IOException {
        return (Map<?, ?>) Json.parse(Files.readString(
                Path.of("..", "specifications", "06-risk", "frtb-ima-backtest-tables.json"))).value();
    }

    private static double num(Object o) {
        return ((Json.Number) o).value();
    }

    @Test
    void sharedTableEqualsSpecFile() throws IOException {
        Map<?, ?> doc = tables();
        List<?> m = (List<?>) doc.get("multiplier_250");
        assertEquals(m.size(), FrtbBacktestTables.MULTIPLIER_250.length);
        for (int i = 0; i < m.size(); i++) {
            assertEquals(num(m.get(i)), FrtbBacktestTables.MULTIPLIER_250[i]);
        }
        assertEquals(num(doc.get("coverage")), FrtbBacktestTables.COVERAGE);
        assertEquals(num(doc.get("amber_from_cumulative")), FrtbBacktestTables.AMBER_FROM);
        assertEquals(num(doc.get("red_from_cumulative")), FrtbBacktestTables.RED_FROM);
        assertEquals(num(doc.get("multiplier_red")), FrtbBacktestTables.MULTIPLIER_RED);
        assertEquals((long) num(doc.get("desk_limit_99")), FrtbBacktestTables.DESK_LIMIT_99);
        assertEquals((long) num(doc.get("desk_limit_975")), FrtbBacktestTables.DESK_LIMIT_975);
        assertEquals((long) num(doc.get("max_observations")), FrtbBacktestTables.MAX_OBSERVATIONS);
        assertEquals((long) num(doc.get("table_observations")), FrtbBacktestTables.TABLE_OBSERVATIONS);
    }

    /** KR-41: MAR99 Table 2 rows 0 to 10, percent to 2 decimals, zone and multiplier as printed. */
    @Test
    void mar99Table2() throws IOException {
        Map<?, ?> doc = tables();
        List<?> pct = (List<?>) doc.get("printed_table2_cumulative_percent");
        List<?> zones = (List<?>) doc.get("printed_table2_zone");
        for (int x = 0; x <= 10; x++) {
            FrtbBacktest.Zone z = FrtbBacktest.zone(250, x, 0);
            assertEquals(num(pct.get(x)), Math.round(z.cumulativeProbability() * 1e4) / 100.0, "row " + x);
            assertEquals(zones.get(x), z.zone());
            double want = x < 10 ? FrtbBacktestTables.MULTIPLIER_250[x] : 2.0;
            assertEquals(want, z.multiplier());
            assertEquals(5, z.amberFrom());
            assertEquals(10, z.redFrom());
        }
        assertEquals(2.0, FrtbBacktest.zone(250, 0, 200).multiplier());
        assertNull(FrtbBacktest.zone(260, 6, 6).multiplier());
        assertEquals("AMBER", FrtbBacktest.zone(1, 0, 0).zone()); // KR-42
    }

    /** The zone boundaries are the first counts whose binomial CDF reaches 95% and 99.99%. */
    @Test
    void zoneBoundaryProperties() {
        Random r = new Random(17);
        for (int i = 0; i < 200; i++) {
            long n = 1 + r.nextInt(3000);
            FrtbBacktest.Zone z = FrtbBacktest.zone(n, 0, 0);
            double p = 0.01;
            assertTrue(FrtbBacktest.binomialCdf(n, z.amberFrom(), p) >= 0.95);
            assertTrue(z.amberFrom() == 0 || FrtbBacktest.binomialCdf(n, z.amberFrom() - 1, p) < 0.95);
            assertTrue(FrtbBacktest.binomialCdf(n, z.redFrom(), p) >= 0.9999);
            assertTrue(z.redFrom() == 0 || FrtbBacktest.binomialCdf(n, z.redFrom() - 1, p) < 0.9999);
            assertTrue(z.amberFrom() <= z.redFrom());
            long x = r.nextInt((int) n + 1);
            String zone = FrtbBacktest.zone(n, x, 0).zone();
            assertEquals(x >= z.redFrom() ? "RED" : x >= z.amberFrom() ? "AMBER" : "GREEN", zone);
        }
        assertEquals(0.0, FrtbBacktest.binomialCdf(10, -1, 0.01));
        assertEquals(1.0, FrtbBacktest.binomialCdf(10, 10, 0.01));
        assertEquals(1, FrtbBacktest.firstAtLeast(FrtbBacktest.binomialPartialSums(1, 0.5), 1, 0.9999));
        // KR-237: only + - * /, so the bits equal the Python reference (frtb_backtest.binomial_cdf); at n = 100,000
        // the lgamma form was 1.3e-10 off the exact rational value (KA-A16).
        assertEquals(0.9448722135510401, FrtbBacktest.binomialCdf(100_000, 1_050, 0.01), 0.0);
        assertEquals(0.8921876269036252, FrtbBacktest.binomialCdf(250, 4, 0.01), 0.0);
        assertEquals(0.9777910867630771, FrtbBacktest.binomialCdf(1_000_000, 10_200, 0.01), 0.0);
    }

    @Test
    void deskLimits() {
        FrtbBacktest.Desk d = FrtbBacktest.desk(250, 12, 10, 30, 28);
        assertTrue(d.eligible());
        assertFalse(d.breach99() || d.breach975());
        assertTrue(FrtbBacktest.desk(250, 13, 0, 0, 0).breach99());
        FrtbBacktest.Desk d31 = FrtbBacktest.desk(250, 0, 0, 0, 31);
        assertTrue(d31.breach975());
        assertFalse(d31.eligible());
        assertEquals(31, d31.exceptions975());
    }

    @Test
    void counting() {
        FrtbBacktest.Count c = FrtbBacktest.countExceptions(Arrays.asList(1.0, 1.0, null, 2.0, 0.5),
                Arrays.asList(-1.0, -1.25, 0.3, null, 0.0), Arrays.asList(-1.5, 0.0, 0.1, -2.5, -0.5));
        assertEquals(List.of(1L, 2L, 3L), c.daysActual());
        assertEquals(List.of(0L, 2L, 3L), c.daysHypothetical());
        assertEquals(3, c.exceptions());
        assertEquals(5, c.observations());
    }

    private static void fails(String code, String field, Runnable r) {
        QfError e = assertThrows(QfError.class, r::run);
        assertEquals(code, e.code());
        assertEquals(field, e.field());
    }

    @Test
    void errors() {
        fails("E_LIMIT", "observations", () -> FrtbBacktest.zone(1_000_001, -1, 0));
        fails("E_DOMAIN", "observations", () -> FrtbBacktest.zone(0, 0, 0));
        fails("E_DOMAIN", "exceptions_actual", () -> FrtbBacktest.zone(10, 11, 0));
        fails("E_DOMAIN", "exceptions_hypothetical", () -> FrtbBacktest.zone(10, 0, -1));
        fails("E_DOMAIN", "exceptions_975_actual", () -> FrtbBacktest.desk(250, 0, 0, 251, 0));
        fails("E_LIMIT", "observations", () -> FrtbBacktest.desk(2_000_000, 0, 0, 0, 0));
        fails("E_INPUT", "var", () -> FrtbBacktest.countExceptions(List.of(), List.of(), List.of()));
        fails("E_INPUT", "actual", () -> FrtbBacktest.countExceptions(List.of(1.0), List.of(), List.of(1.0)));
        fails("E_INPUT", "hypothetical", () -> FrtbBacktest.countExceptions(List.of(1.0), List.of(1.0), List.of()));
    }

    /**
     * Audit KF-21 (2026-11-20): the double-double power against exact binary64 results (a^n / 2^(kn) rounded
     * once, exact integer arithmetic). Plain binary64 powering differs on each case (0.999999^1,000,000 gives
     * 0.36787925722078507), so a plain loop fails here.
     */
    @Test
    void powerIsTheCorrectlyRoundedBinary64Result() {
        assertEquals(0.08105851616218128, FrtbBacktest.power(0.99, 250), 0.0);
        assertEquals(0.6983372960937497, FrtbBacktest.power(0.95, 7), 0.0);
        assertEquals(4.5381772136224775e-05, FrtbBacktest.power(0.9999, 99_999), 0.0);
        assertEquals(0.36787925722106646, FrtbBacktest.power(0.999999, 1_000_000), 0.0);
        assertEquals(0.95, FrtbBacktest.power(0.95, 1), 0.0);
    }
}
