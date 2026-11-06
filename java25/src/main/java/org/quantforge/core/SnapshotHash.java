package org.quantforge.core;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

/** Canonical byte form and identity of a snapshot document (snapshot-hash.md). */
public final class SnapshotHash {
    private SnapshotHash() {}

    public record Result(String canonical, String snapshotId) {}

    public static Result hash(String documentText) {
        Json.Document doc = Json.parse(documentText);
        if (doc.numberOverflow()) {
            throw new QfError("E_SCHEMA", "number overflows binary64", "document_text");
        }
        if (doc.loneSurrogate()) {
            throw new QfError("E_SCHEMA", "lone surrogate escape", "document_text");
        }
        if (!(doc.value() instanceof Map<?, ?> top)) {
            throw new QfError("E_SCHEMA", "top level is not an object", "document_text");
        }
        StringBuilder b = new StringBuilder();
        object(b, top, true);
        String canonical = b.toString();
        try {
            byte[] sum = MessageDigest.getInstance("SHA-256").digest(canonical.getBytes(StandardCharsets.UTF_8));
            return new Result(canonical, "sha256:" + HexFormat.of().formatHex(sum));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private static void value(StringBuilder b, Object v) {
        switch (v) {
            case null -> b.append("null");
            case Boolean x -> b.append(x.booleanValue());
            case Json.Number x -> {
                double d = x.value() == 0.0 ? 0.0 : x.value();
                b.append('#').append(String.format("%016x", Double.doubleToRawLongBits(d)));
            }
            case String x -> string(b, x);
            case List<?> x -> {
                b.append('[');
                for (int k = 0; k < x.size(); k++) {
                    if (k > 0) {
                        b.append(',');
                    }
                    value(b, x.get(k));
                }
                b.append(']');
            }
            case Map<?, ?> x -> object(b, x, false);
            default -> throw new IllegalArgumentException("unexpected value");
        }
    }

    private static void object(StringBuilder b, Map<?, ?> m, boolean top) {
        List<String> keys = new ArrayList<>();
        for (Object k : m.keySet()) {
            if (!(top && k.equals("snapshot_id"))) {
                keys.add((String) k);
            }
        }
        keys.sort((p, q) -> Arrays.compareUnsigned(p.getBytes(StandardCharsets.UTF_8), q.getBytes(StandardCharsets.UTF_8)));
        b.append('{');
        boolean first = true;
        for (String k : keys) {
            if (!first) {
                b.append(',');
            }
            first = false;
            string(b, k);
            b.append(':');
            value(b, m.get(k));
        }
        b.append('}');
    }

    private static void string(StringBuilder b, String t) {
        b.append('"');
        for (int k = 0; k < t.length(); k++) {
            char c = t.charAt(k);
            if (c == '"' || c == '\\') {
                b.append('\\').append(c);
            } else if (c < 0x20) {
                b.append(String.format("\\u%04x", (int) c));
            } else {
                b.append(c);
            }
        }
        b.append('"');
    }
}
