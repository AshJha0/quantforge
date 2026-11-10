package org.quantforge.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** Malformed-input and writer edge cases of the strict JSON reader. */
class JsonErrorPathTest {
    private static void bad(String text) {
        assertEquals("E_PARSE", assertThrows(QfError.class, () -> Json.parse(text)).code(), text);
    }

    private static String roundTrip(Object v) {
        StringBuilder b = new StringBuilder();
        Json.write(b, v);
        return b.toString();
    }

    @Test
    void malformedObjectsRejected() {
        bad("{1:2}");
        bad("{\"a\" 1}");
        bad("{\"a\":1 \"b\":2}");
        bad("{\"a\":1,\"a\":2}");
        bad("{\"o\":{\"k\":1,\"k\":2}}");
        bad("{\"a\":1} x");
    }

    @Test
    void badEscapesRejected() {
        bad("\"\\q\"");
        bad("\"\\u12\"");
        bad("\"\\u12G4\"");
        bad("\"\\u12\u00e94\"");
    }

    @Test
    void escapesDecode() {
        assertEquals("\"\\/\b\f\n\r\t\u00e9", Json.parse("\"\\\"\\\\\\/\\b\\f\\n\\r\\t\\u00e9\"").value());
    }

    @Test
    void loneSurrogateFlagged() {
        assertTrue(Json.parse("\"\\ud800\"").loneSurrogate());
        assertFalse(Json.parse("\"\\ud83d\\ude00\"").loneSurrogate());
    }

    @Test
    void depthScan() {
        assertTrue(Json.nestsDeeperThan("[[[]]]", 2));
        assertFalse(Json.nestsDeeperThan("[[[]]]", 3));
        assertFalse(Json.nestsDeeperThan("[\"[[[[\\\"[[\"]", 1));
        assertEquals(3, Json.depth(Json.parse("{\"a\":[{}]}").value()));
        assertEquals(0, Json.depth(1.0));
    }

    @Test
    void writerEdgeCases() {
        assertEquals("null", roundTrip(Double.NaN));
        assertEquals("null", roundTrip(Double.NEGATIVE_INFINITY));
        assertEquals("\"a\\\"b\\\\c\\u0001\"", roundTrip("a\"b\\c\u0001"));
        assertEquals("[1.5,null]", roundTrip(java.util.Arrays.asList(1.5, null)));
        assertEquals("{\"k\":[]}", roundTrip(Map.of("k", List.of())));
        assertThrows(IllegalArgumentException.class, () -> roundTrip(new Object()));
    }
}
