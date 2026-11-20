package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;

/**
 * Targeted proof for the stage K wave 2b extraction of {@code FrtbSbm.bucketRadicand} and {@code crossRadicand}: every
 * golden case of a registered FRTB sensitivity-based verb ({@code risk.frtb.*} apart from backtesting), in every suite
 * that holds one, replayed through {@link Main#handle} and judged by {@link GoldenSuiteTest#judge}, exactly as
 * GoldenSuiteTest does for the whole tree. The case set is read from the files.
 */
class FrtbAggregationReplayTest {
    private static final Path GOLDEN = Path.of("..", "datasets", "golden");

    private static Object plain(Object v) {
        return switch (v) {
            case Json.Number n -> n.isIntegerForm() ? (Object) (long) n.value() : (Object) n.value();
            case List<?> l -> l.stream().map(FrtbAggregationReplayTest::plain)
                    .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
            case Map<?, ?> m -> {
                Map<String, Object> out = new LinkedHashMap<>();
                m.forEach((k, x) -> out.put((String) k, plain(x)));
                yield out;
            }
            case null, default -> v;
        };
    }

    @Test
    void everyFrtbSensitivityCase() throws IOException {
        List<Path> files;
        try (Stream<Path> s = Files.walk(GOLDEN)) {
            files = s.filter(p -> p.toString().endsWith(".json")).sorted().toList();
        }
        List<String> failures = new ArrayList<>();
        int replayed = 0;
        for (Path f : files) {
            Object doc = Json.parse(Files.readString(f)).value();
            if (!(doc instanceof Map<?, ?> d) || !(d.get("cases") instanceof List<?> cases)) {
                continue;
            }
            Map<String, Map<?, ?>> results = new HashMap<>();
            for (Object o : cases) {
                Map<?, ?> c = (Map<?, ?>) o;
                String op = String.valueOf(c.get("operation"));
                if (!op.startsWith("risk.frtb.") || op.startsWith("risk.frtb.backtest.")
                        || Operations.find(op) == null) {
                    continue;
                }
                Map<String, Object> envelope = new LinkedHashMap<>();
                envelope.put("schema_version", "1.0");
                envelope.put("case_id", c.get("case_id"));
                envelope.put("operation", op);
                envelope.put("inputs", plain(c.get("inputs")));
                StringBuilder b = new StringBuilder();
                Json.write(b, envelope);
                Map<?, ?> result = (Map<?, ?>) Json.parse(Main.handle(b.toString()).json()).value();
                results.put(String.valueOf(c.get("case_id")), result);
                String problem = GoldenSuiteTest.judge(c, result, results);
                if (problem != null) {
                    failures.add(f.getFileName() + " " + c.get("case_id") + ": " + problem);
                }
                replayed++;
            }
        }
        System.out.println("FRTB-REPLAY: " + replayed + " cases");
        assertTrue(replayed > 0);
        assertTrue(failures.isEmpty(), () -> failures.size() + " failures: " + failures);
    }
}
