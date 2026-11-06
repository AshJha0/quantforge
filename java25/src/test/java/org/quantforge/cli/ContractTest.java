package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/** Exit codes, envelope handling and batch behaviour from cli-contract.md. */
class ContractTest {
    private static final String GOOD = "{\"schema_version\":\"1.0\",\"case_id\":\"c1\",\"operation\":"
            + "\"core.daycount.year_fraction\",\"inputs\":{\"convention\":\"ACT_360\",\"start\":\"2024-01-01\",\"end\":\"2024-07-01\"}}";

    private record Run(int code, String out) {}

    private static Run run(String stdin, String... args) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int code = Main.run(args, new ByteArrayInputStream(stdin.getBytes(StandardCharsets.UTF_8)), out);
        return new Run(code, out.toString(StandardCharsets.UTF_8));
    }

    private static String code(String doc) {
        return Main.handle(doc).json().replaceAll(".*\"code\":\"(E_[A-Z_]+)\".*\\s*", "$1");
    }

    @Test
    void runGivesZeroOnOkAndTwoOnError() throws IOException {
        Run ok = run(GOOD, "run");
        assertEquals(0, ok.code());
        assertTrue(ok.out().contains("\"year_fraction\":0.5055555555555555"));
        assertEquals(2, run("{", "run").code());
    }

    @Test
    void unknownCommandIsSixtyFourWithEmptyStdout() throws IOException {
        Run r = run("", "nonsense");
        assertEquals(64, r.code());
        assertEquals("", r.out());
        assertEquals(64, run("").code());
    }

    @Test
    void batchKeepsGoingPastABadLine() throws IOException {
        Run r = run(GOOD + "\nnot json\n" + GOOD + "\n", "batch");
        assertEquals(0, r.code());
        String[] lines = r.out().split("\n");
        assertEquals(3, lines.length);
        assertTrue(lines[1].contains("E_PARSE") && lines[1].contains("\"case_id\":\"unknown\""));
        assertEquals(lines[0], lines[2]);
    }

    @Test
    void versionAndOperations() throws IOException {
        assertTrue(run("", "version").out().contains("\"contract_version\":\"1.0.0\""));
        assertTrue(run("", "operations").out().contains("\"core.ts.ar1\""));
    }

    @Test
    void envelopeErrors() {
        assertEquals("E_PARSE", code("{\"a\":1,\"a\":2}"));
        assertEquals("E_SCHEMA", code("[]"));
        assertEquals("E_SCHEMA", code("{\"schema_version\":\"1.0\",\"case_id\":\"x\",\"operation\":\"core.a\"}"));
        assertEquals("E_SCHEMA", code(GOOD.replace("\"inputs\":{", "\"inputs\":{\"z\":1e400,")));
        assertEquals("E_UNSUPPORTED_OPERATION", code(GOOD.replace("core.daycount.year_fraction", "core.no.such")));
    }

    @Test
    void overflowedStartIsAnErrorForEveryMethod() {
        for (String method : new String[] {"BFGS", "GAUSS_NEWTON", "LEVENBERG_MARQUARDT"}) {
            String c = "{\"schema_version\":\"1.0\",\"case_id\":\"x\",\"operation\":\"calib.fit\",\"inputs\":"
                    + "{\"model\":\"ROSENBROCK\",\"x\":[],\"y\":[],\"start\":[-1.2e+300,1.0],\"method\":\"" + method + "\"}}";
            assertEquals("E_NON_FINITE", code(c));
        }
    }

    @Test
    void nonFiniteResultIsReported() {
        String c = "{\"schema_version\":\"1.0\",\"case_id\":\"x\",\"operation\":\"core.integrate.trapezoid\","
                + "\"inputs\":{\"function\":\"inv_sqrt\",\"a\":0,\"b\":1,\"n\":4}}";
        assertEquals("E_NON_FINITE", code(c));
        assertFalse(Main.handle(c).ok());
    }
}
