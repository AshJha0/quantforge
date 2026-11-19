package org.quantforge.risk;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

/**
 * Stage K wave 1 acceptance evidence: when QF_K_EVIDENCE names a file, each acceptance test appends one JSON line
 * {"key": ..., "value": ...} (program/stage_k_w1/acceptance_java.jsonl is written this way).
 */
public final class StageKEvidence {
    private StageKEvidence() {}

    public static void write(String key, String json) {
        String path = System.getenv("QF_K_EVIDENCE");
        if (path == null || path.isEmpty()) {
            return;
        }
        try {
            Files.writeString(Path.of(path), "{\"key\": \"" + key + "\", \"value\": " + json + "}\n",
                    StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }
}
