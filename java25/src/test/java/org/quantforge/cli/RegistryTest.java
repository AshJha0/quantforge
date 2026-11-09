package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** G4: the verb table comes from the registry, modules are named by domain, and a duplicate verb is refused. */
class RegistryTest {
    @Test
    void verbTableIsTheRegistry() {
        Map<String, String> table = Operations.REGISTRY.table();
        assertEquals(table.keySet(), Operations.names());
        assertFalse(table.isEmpty());
        for (String d : table.values()) {
            assertFalse(d.matches(".*stage.*|.*_[a-f][0-9]*$"), d);
        }
    }

    @Test
    void duplicateVerbOrModuleIsRefused() {
        Registry.Module a = new Registry.Module("a", t -> t.put("x.y.z", in -> null));
        Registry.Module b = new Registry.Module("b", t -> t.put("x.y.z", in -> null));
        assertThrows(IllegalStateException.class, () -> Registry.of(List.of(a, b)));
        assertThrows(IllegalStateException.class, () -> Registry.of(List.of(a, a)));
        assertTrue(Registry.of(List.of(a)).names().contains("x.y.z"));
    }
}
