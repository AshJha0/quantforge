package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import org.quantforge.core.Json;

/**
 * The stage I tutorial inputs ({@code examples/hedge_*_i.json}, handover follow-up note to waves 1 to 4d): each file
 * is run through the CLI's request handler, as {@code quantforge run} does, and must return {@code status: ok} with
 * the outputs of the golden case it was copied from.
 */
class HedgeExamplesSmokeTest {
    private static final Path EXAMPLES = Path.of("..", "examples");
    private static final Path GOLDEN = Path.of("..", "datasets", "golden", "stage_i");

    /** Example file, golden suite, golden case: the table of the follow-up note. */
    private static final List<String[]> TABLE = List.of(
            new String[] {"hedge_greeks_i.json", "hedgegreeks_i", "hedgegreeks_i-0003"},
            new String[] {"hedge_minvar_i.json", "hedgemv_i", "hedgemv_i-0006"},
            new String[] {"hedge_beta_i.json", "hedgebeta_i", "hedgebeta_i-0001"},
            new String[] {"hedge_qp_keyrate_i.json", "hedgeqp_i", "hedgeqp_i-0009"},
            new String[] {"hedge_qp_minnorm_i.json", "hedgeqp_i", "hedgeqp_i-0018"},
            new String[] {"hedge_integer_i.json", "hedgeint_i", "hedgeint_i-0010"},
            new String[] {"hedge_residual_i.json", "hedgeres_i", "hedgeres_i-0002"},
            new String[] {"hedge_credit_i.json", "hedgecredit_i", "hedgecredit_i-0004"},
            new String[] {"hedge_correlation_i.json", "hedgecorr_i", "hedgecorr_i-0003"},
            new String[] {"hedge_crossasset_i.json", "hedgexa_i", "hedgexa_i-0002"},
            new String[] {"hedge_cost_i.json", "hedgecost_i", "hedgecost_i-0002"},
            new String[] {"hedge_frontier_i.json", "hedgefrontier_i", "hedgefrontier_i-0001"},
            new String[] {"hedge_backtest_i.json", "hedgebt_i", "hedgebt_i-0001"},
            new String[] {"hedge_effectiveness_i.json", "hedgeeff_i", "hedgeeff_i-0001"},
            new String[] {"hedge_select_i.json", "hedgeselect_i", "hedgeselect_i-0009"},
            new String[] {"hedge_slippage_i.json", "hedgeslip_i", "hedgeslip_i-0003"});

    @TestFactory
    Stream<DynamicTest> everyExample() throws IOException {
        try (Stream<Path> s = Files.list(EXAMPLES)) {
            long files = s.filter(p -> p.getFileName().toString().matches("hedge_.*_i\\.json")).count();
            assertEquals(TABLE.size(), files, "every examples/hedge_*_i.json file is in the table");
        }
        return TABLE.stream().map(row -> DynamicTest.dynamicTest(row[0], () -> run(row)));
    }

    private static void run(String[] row) throws IOException {
        Map<?, ?> golden = null;
        for (Object o : (List<?>) ((Map<?, ?>) Json.parse(Files.readString(GOLDEN.resolve(row[1] + ".json"))).value())
                .get("cases")) {
            if (row[2].equals(((Map<?, ?>) o).get("case_id"))) {
                golden = (Map<?, ?>) o;
            }
        }
        assertNotNull(golden, row[2]);
        Map<?, ?> request = (Map<?, ?>) Json.parse(Files.readString(EXAMPLES.resolve(row[0]))).value();
        assertEquals(golden.get("operation"), request.get("operation"));
        Map<?, ?> result = (Map<?, ?>) Json.parse(Main.handle(Files.readString(EXAMPLES.resolve(row[0]))).json())
                .value();
        assertEquals("ok", result.get("status"), () -> row[0] + ": " + result);
        assertNull(GoldenSuiteTest.judge(golden, result, new HashMap<>()), row[0]);
    }
}
