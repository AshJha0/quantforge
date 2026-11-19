package org.quantforge.paper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;

/**
 * The decimal readers, the Python-style truthiness and int conversions, and the canonical JSON writer of the
 * paper port, on every input type they accept or refuse (paper-trading.md, HR-12, HR-44; Python reference
 * {@code quantforge_core.paper}).
 */
class PaperHelpersTest {

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    @Test
    void parseReadsDecimalsAndRefusesTheRest() {
        assertEquals(new BigDecimal("12.5"), Paper.parse(" 12.5 ", "p"));
        assertEquals("E_SCHEMA", code(() -> Paper.parse("NaN", "p")));
        assertEquals("E_SCHEMA", code(() -> Paper.parse("-Infinity", "p")));
        assertEquals("E_PARSE", code(() -> Paper.parse("12,5", "p")));
        assertEquals("E_PARSE", code(() -> Paper.parse("abc", "p")));
    }

    @Test
    void decTakesStringsAndIntegersOnly() {
        assertEquals(new BigDecimal("3.25"), Paper.dec("3.25", "q"));
        assertEquals(new BigDecimal(7), Paper.dec(7L, "q"));
        assertEquals(new BigDecimal(7), Paper.dec(7, "q"));
        assertEquals(new BigDecimal(9), Paper.dec(new Json.Number(9.0, "9"), "q"));
        assertEquals(new BigDecimal("1.5"), Paper.dec(new BigDecimal("1.5"), "q"));
        assertEquals("E_INPUT", code(() -> Paper.dec(Boolean.TRUE, "q")));
        assertEquals("E_INPUT", code(() -> Paper.dec(new Json.Number(1.5, "1.5"), "q")));
        assertEquals("E_PARSE", code(() -> Paper.dec(null, "q")));
        assertEquals("E_PARSE", code(() -> Paper.dec(List.of(), "q")));
    }

    @Test
    void truthyFollowsPython() {
        assertFalse(Paper.truthy(null));
        assertFalse(Paper.truthy(Boolean.FALSE));
        assertTrue(Paper.truthy(Boolean.TRUE));
        assertFalse(Paper.truthy(""));
        assertTrue(Paper.truthy("x"));
        assertFalse(Paper.truthy(new Json.Number(0.0, "0")));
        assertTrue(Paper.truthy(new Json.Number(2.0, "2")));
        assertFalse(Paper.truthy(List.of()));
        assertTrue(Paper.truthy(List.of(1)));
        assertFalse(Paper.truthy(Map.of()));
        assertTrue(Paper.truthy(Map.of("a", 1)));
        assertTrue(Paper.truthy(5L));
    }

    @Test
    void pyIntFollowsPython() {
        assertEquals(BigInteger.ONE, Paper.pyInt(Boolean.TRUE, "n"));
        assertEquals(BigInteger.ZERO, Paper.pyInt(Boolean.FALSE, "n"));
        assertEquals(BigInteger.valueOf(3), Paper.pyInt(new Json.Number(3.7, "3.7"), "n"));
        assertEquals(BigInteger.valueOf(4), Paper.pyInt(4L, "n"));
        assertEquals(BigInteger.valueOf(12), Paper.pyInt(" 12 ", "n"));
        assertEquals("E_INPUT", code(() -> Paper.pyInt("1.5", "n")));
        assertEquals("E_INPUT", code(() -> Paper.pyInt(null, "n")));
    }

    @Test
    void canonicalWriterSortsKeysAndWritesEveryType() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("b", List.of(1, 2L, Boolean.TRUE));
        m.put("a", null);
        m.put("c", new Json.Number(5.0, "5"));
        List<Object> l = new ArrayList<>();
        l.add("xé");
        m.put("d", l);
        StringBuilder b = new StringBuilder();
        Paper.writeCanonical(b, m);
        assertEquals("{\"a\":null,\"b\":[1,2,true],\"c\":5,\"d\":[\"x\\u00e9\"]}", b.toString());
    }
}
