package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import org.quantforge.core.Json;

/** Runs every oracle case through the CLI layer in process. The neutral runner stays the official check. */
class GoldenSuiteTest {
    private static final Path GOLDEN = Path.of("..", "datasets", "golden", "core");

    /** Cases that contradict the spec text; see SPEC_QUESTIONS.md. Each must still disagree, so a fix is noticed. */
    private static final Set<String> DISPUTED = Set.of("daycount-1472",
            "calendar-0056", "calendar-0057", "calendar-0061", "calendar-0084", "calendar-0107", "calendar-0148",
            "calendar-0149", "calendar-0180", "calendar-0314", "calendar-0318", "calendar-0608", "calendar-0609",
            "calendar-0613", "calendar-0636", "calendar-0659", "calendar-0700", "calendar-0701", "calendar-0732",
            "calendar-0866", "calendar-0870");

    /** absolute, relative; null means exact. Mirrors conformance/tolerances/policy.yaml. */
    private static final Map<String, double[]> CLASSES = Map.of(
            "date_and_convention", new double[0], "bit_exact", new double[0],
            "simple_analytic", new double[] {1e-12, 1e-10}, "interpolation", new double[] {1e-10, 1e-8},
            "root_finding", new double[] {1e-10, 1e-10}, "quadrature", new double[] {1e-11, 1e-10},
            "statistics", new double[] {1e-11, 1e-10}, "numerical_scheme", new double[] {1e-8, 1e-8},
            "fourier", new double[] {1e-9, 1e-9}, "common_rng", new double[] {1e-9, 1e-9});

    @TestFactory
    Stream<DynamicTest> everySuite() throws IOException {
        List<Path> files;
        try (Stream<Path> s = Files.list(GOLDEN)) {
            files = s.sorted().toList();
        }
        assertEquals(16, files.size());
        return files.stream().map(p -> DynamicTest.dynamicTest(p.getFileName().toString(), () -> suite(p)));
    }

    private static Map<?, ?> map(Object o) {
        return (Map<?, ?>) o;
    }

    private static void suite(Path file) throws IOException {
        Map<?, ?> doc = map(Json.parse(Files.readString(file)).value());
        List<String> failures = new ArrayList<>();
        for (Object o : (List<?>) doc.get("cases")) {
            Map<?, ?> c = map(o);
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("schema_version", "1.0");
            envelope.put("case_id", c.get("case_id"));
            envelope.put("operation", c.get("operation"));
            envelope.put("inputs", plain(c.get("inputs")));
            StringBuilder b = new StringBuilder();
            Json.write(b, envelope);
            Map<?, ?> result = map(Json.parse(Main.handle(b.toString()).json()).value());
            String problem = judge(c, result);
            boolean disputed = DISPUTED.contains(c.get("case_id"));
            if (disputed == (problem == null)) {
                failures.add(c.get("case_id") + ": " + (disputed ? "disputed case now agrees" : problem));
            }
        }
        assertTrue(failures.isEmpty(), () -> failures.size() + " failures, first: " + failures.getFirst());
    }

    /** Turns parsed numbers back into writable values, keeping integer form. */
    private static Object plain(Object v) {
        return switch (v) {
            case Json.Number n -> n.isIntegerForm() ? (Object) (long) n.value() : (Object) n.value();
            case List<?> l -> l.stream().map(GoldenSuiteTest::plain).collect(java.util.stream.Collectors.toCollection(ArrayList::new));
            case Map<?, ?> m -> {
                Map<String, Object> out = new LinkedHashMap<>();
                m.forEach((k, x) -> out.put((String) k, plain(x)));
                yield out;
            }
            case null, default -> v;
        };
    }

    private static String judge(Map<?, ?> c, Map<?, ?> result) {
        Map<?, ?> expected = map(c.get("expected"));
        if ("error".equals(expected.get("status"))) {
            Object code = result.get("error") == null ? null : map(result.get("error")).get("code");
            return expected.get("error_code").equals(code) ? null : "expected " + expected.get("error_code") + ", got " + result;
        }
        if (!"ok".equals(result.get("status"))) {
            return "unexpected " + result.get("error");
        }
        Map<?, ?> want = map(expected.get("outputs"));
        Map<?, ?> got = map(result.get("outputs"));
        if (!want.keySet().equals(got.keySet())) {
            return "keys " + got.keySet();
        }
        Map<?, ?> per = c.get("output_classes") == null ? Map.of() : map(c.get("output_classes"));
        for (Object k : want.keySet()) {
            String cls = (String) (per.containsKey(k) ? per.get(k) : c.get("tolerance_class"));
            double[] tol = CLASSES.get(cls).clone();
            if (!per.containsKey(k) && c.get("tolerance_limit") != null) {
                Map<?, ?> limit = map(c.get("tolerance_limit"));
                tol = new double[] {
                    limit.get("absolute") instanceof Json.Number a ? a.value() : tol[0],
                    limit.get("relative") instanceof Json.Number r ? r.value() : tol[1]};
            }
            String p = same(got.get(k), want.get(k), tol, String.valueOf(k));
            if (p != null) {
                return p;
            }
        }
        return null;
    }

    private static String same(Object a, Object e, double[] tol, String path) {
        if (e instanceof Map<?, ?> m) {
            for (Object k : m.keySet()) {
                String p = same(map(a).get(k), m.get(k), tol, path + "." + k);
                if (p != null) {
                    return p;
                }
            }
            return null;
        }
        if (e instanceof List<?> l) {
            List<?> x = (List<?>) a;
            if (x.size() != l.size()) {
                return path + " length";
            }
            for (int i = 0; i < l.size(); i++) {
                String p = same(x.get(i), l.get(i), tol, path + "[" + i + "]");
                if (p != null) {
                    return p;
                }
            }
            return null;
        }
        if (e instanceof Json.Number n && a instanceof Json.Number v) {
            double x = v.value();
            double y = n.value();
            boolean ok = tol.length == 0 ? x == y
                    : Math.abs(x - y) <= tol[0] + tol[1] * Math.max(Math.abs(x), Math.abs(y));
            return ok ? null : path + ": " + x + " vs " + y;
        }
        return java.util.Objects.equals(a, e) ? null : path + ": " + a + " vs " + e;
    }
}
