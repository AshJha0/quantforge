package org.quantforge.core;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** Ruling G9: the compiled table must equal the spec's data file. */
class SobolDataTest {
    private static int number(Object o) {
        return (int) ((Json.Number) o).value();
    }

    @Test
    void compiledTableEqualsSpecFile() throws IOException {
        Path file = Path.of("..", "specifications", "01-core", "data", "sobol-joe-kuo-d6-64.json");
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(file)).value();
        List<?> dims = (List<?>) doc.get("dimensions");
        assertEquals(SobolData.S.length, dims.size());
        for (int i = 0; i < dims.size(); i++) {
            Map<?, ?> d = (Map<?, ?>) dims.get(i);
            assertEquals(number(d.get("s")), SobolData.S[i]);
            assertEquals(number(d.get("a")), SobolData.A[i]);
            int[] m = ((List<?>) d.get("m")).stream().mapToInt(SobolDataTest::number).toArray();
            assertArrayEquals(m, SobolData.M[i]);
        }
    }
}
