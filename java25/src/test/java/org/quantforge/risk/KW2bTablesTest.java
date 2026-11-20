package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;

/** The generated {@link KW2bTables} equals the `entries` of the three JSON tables (KR-50), order included. */
class KW2bTablesTest {
    private static final Path DIR = Path.of("..", "specifications", "tables", "stage_k");

    /** The parsed JSON value with numbers as Long (integers) or Double, as the generator writes them. */
    private static Object plain(Object v) {
        if (v instanceof Json.Number n) {
            return n.isIntegerForm() ? (Object) (long) n.value() : (Object) n.value();
        }
        if (v instanceof List<?> l) {
            List<Object> out = new ArrayList<>();
            l.forEach(x -> out.add(plain(x)));
            return out;
        }
        if (v instanceof Map<?, ?> m) {
            Map<Object, Object> out = new java.util.LinkedHashMap<>();
            m.forEach((k, x) -> out.put(k, plain(x)));
            return out;
        }
        return v;
    }

    private static void same(String file, Map<String, Object> held) throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(DIR.resolve(file))).value();
        List<Object> keys = new ArrayList<>();
        for (Object e : (List<?>) doc.get("entries")) {
            Map<?, ?> entry = (Map<?, ?>) e;
            keys.add(entry.get("key"));
            assertEquals(plain(entry.get("value")), held.get((String) entry.get("key")), file + " " + entry.get("key"));
        }
        assertEquals(keys, new ArrayList<>(held.keySet()), file + ": keys and order");
    }

    @Test
    void generatedTreesEqualTheJson() throws IOException {
        same("mar50_cva.json", KW2bTables.MAR50);
        same("lev_leverage.json", KW2bTables.LEV);
        same("lex_large_exposures.json", KW2bTables.LEX);
        assertTrue(Cva.SECTORS.size() == 8 && Cva.CCS_BUCKETS.contains("1a"));
    }
}
