package org.quantforge.cli;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.regex.Pattern;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;

/** The quantforge command line (cli-contract.md). */
public final class Main {
    private Main() {}

    private static final String CONTRACT = "1.12.0";
    private static final String VERSION = "0.8.0"; // keep equal to <version> in java25/pom.xml
    private static final int MAX_CASE_DEPTH = 80;
    private static final Set<String> ENVELOPE = Set.of("schema_version", "case_id", "operation", "inputs");
    private static final Pattern SCHEMA_VERSION = Pattern.compile("[0-9]+\\.[0-9]+");
    private static final Pattern OPERATION = Pattern.compile("[a-z0-9_]+(\\.[a-z0-9_]+)+");

    /** A result line and whether its status is "ok". */
    record Reply(String json, boolean ok) {}

    public static void main(String[] args) throws IOException {
        int code;
        try {
            code = run(args, System.in, System.out);
        } catch (RuntimeException | StackOverflowError | OutOfMemoryError e) {
            System.err.println("internal fault: " + e);
            code = 70;
        }
        System.out.flush();
        System.exit(code);
    }

    static int run(String[] args, InputStream in, OutputStream out) throws IOException {
        boolean timings = args.length == 2 && args[1].equals("--timings")
                && (args[0].equals("run") || args[0].equals("batch") || args[0].equals("--batch"));
        if (args.length != 1 && !timings) {
            System.err.println("usage: quantforge run|batch|--batch [--timings] | version | operations");
            return 64;
        }
        switch (args[0]) {
            case "run" -> {
                byte[] bytes = in.readAllBytes();
                long t0 = System.nanoTime();
                Reply r = handle(decode(bytes), timings, t0);
                write(out, r.json());
                return r.ok() ? 0 : 2;
            }
            case "batch", "--batch" -> {
                batch(in, out, timings);
                return 0;
            }
            case "version" -> {
                Map<String, Object> v = new LinkedHashMap<>();
                v.put("language", "java");
                v.put("implementation_version", VERSION);
                v.put("contract_version", CONTRACT);
                v.put("toolchain", "JDK " + Runtime.version());
                write(out, json(v));
                return 0;
            }
            case "operations" -> {
                write(out, json(new ArrayList<>(Operations.names())));
                return 0;
            }
            default -> {
                System.err.println("unknown command " + args[0]);
                return 64;
            }
        }
    }

    /** BT5: the longest line (after a trailing CR is removed) that is parsed at all. */
    static final int MAX_LINE_BYTES = 16_777_216;

    private static void batch(InputStream raw, OutputStream out, boolean timings) throws IOException {
        BufferedInputStream in = new BufferedInputStream(raw, 1 << 16);
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        long length = 0; // bytes seen on this line, a trailing CR included
        int last = -1; // last byte seen on this line
        int b;
        while ((b = in.read()) >= 0) {
            if (b == '\n') {
                endLine(out, line, length, last, timings);
                line.reset();
                length = 0;
                last = -1;
            } else {
                length++;
                last = b;
                // Hold at most the limit plus one possible trailing CR; drop the rest of an overlong line.
                if (length <= MAX_LINE_BYTES + 1L) {
                    line.write(b);
                }
            }
        }
        if (length > 0) {
            endLine(out, line, length, last, timings);
        }
    }

    private static void endLine(OutputStream out, ByteArrayOutputStream line, long length, int last, boolean timings)
            throws IOException {
        long t0 = System.nanoTime();
        long content = last == '\r' ? length - 1 : length;
        if (content > MAX_LINE_BYTES) {
            QfError e = new QfError("E_LIMIT", "line is longer than " + MAX_LINE_BYTES + " bytes");
            write(out, errorReply("unknown", e, timings, t0).json());
            return;
        }
        write(out, handle(decode(line.toByteArray()), timings, t0).json());
    }

    private static void write(OutputStream out, String text) throws IOException {
        out.write(text.getBytes(StandardCharsets.UTF_8));
        out.write('\n');
        out.flush();
    }

    /** Returns null for bytes that are not UTF-8; {@link #handle} reports that as a parse error. */
    private static String decode(byte[] bytes) {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes)).toString();
        } catch (CharacterCodingException e) {
            return null;
        }
    }

    private static String json(Object v) {
        StringBuilder b = new StringBuilder();
        Json.write(b, v);
        return b.toString();
    }

    /** Handles one case document. A calculation or schema failure is a result, never an exception. */
    static Reply handle(String text) {
        return handle(text, false, 0L);
    }

    /** As {@link #handle(String)}; with {@code timings}, adds diagnostics.elapsed_ns measured from {@code t0}. */
    static Reply handle(String text, boolean timings, long t0) {
        String caseId = "unknown";
        try {
            if (text == null) {
                throw new QfError("E_PARSE", "input is not UTF-8");
            }
            if (Json.nestsDeeperThan(text, MAX_CASE_DEPTH)) {
                throw new QfError("E_LIMIT", "case is nested too deeply");
            }
            Json.Document doc = Json.parse(text);
            if (doc.value() instanceof Map<?, ?> m && m.get("case_id") instanceof String id && !id.isEmpty()) {
                caseId = id;
            }
            if (doc.numberOverflow()) {
                throw new QfError("E_SCHEMA", "a number overflows binary64");
            }
            if (!(doc.value() instanceof Map<?, ?> envelope)) {
                throw new QfError("E_SCHEMA", "case is not an object");
            }
            Function<In, Operations.Out> op = checkEnvelope(envelope);
            Operations.Out result = apply(op, new In((Map<?, ?>) envelope.get("inputs")));
            if (!finite(result.outputs())) {
                throw new QfError("E_NON_FINITE", "a result is NaN or infinite");
            }
            Map<String, Object> r = header(caseId, "ok");
            r.put("outputs", result.outputs());
            Map<String, Object> diag = new LinkedHashMap<>();
            if (result.diagnostics() != null) {
                for (Map.Entry<?, ?> d : result.diagnostics().entrySet()) {
                    diag.put(String.valueOf(d.getKey()), d.getValue());
                }
            }
            if (timings) {
                diag.put("elapsed_ns", elapsed(t0));
            }
            r.put("diagnostics", diag);
            return new Reply(json(r), true);
        } catch (QfError e) {
            return errorReply(caseId, e, timings, t0);
        }
    }

    private static long elapsed(long t0) {
        return Math.max(0L, System.nanoTime() - t0);
    }

    private static Reply errorReply(String caseId, QfError e, boolean timings, long t0) {
        Map<String, Object> err = new LinkedHashMap<>();
        err.put("code", e.code());
        err.put("message", String.valueOf(e.getMessage()));
        if (e.field() != null) {
            err.put("field", e.field());
        }
        Map<String, Object> r = header(caseId, "error");
        r.put("error", err);
        // Always present (may be empty), so a --timings result minus elapsed_ns equals the untimed one.
        Map<String, Object> diag = new LinkedHashMap<>();
        if (timings) {
            diag.put("elapsed_ns", elapsed(t0));
        }
        r.put("diagnostics", diag);
        return new Reply(json(r), false);
    }

    /**
     * Runs an operation. Any that does more than one linear pass gates itself before starting (ruling B24). For the
     * rest the general array limit is settled here: it outranks a rule error, but not E_SCHEMA.
     */
    private static Operations.Out apply(Function<In, Operations.Out> op, In in) {
        try {
            Operations.Out out = op.apply(in);
            in.gate();
            return out;
        } catch (QfError e) {
            if (in.pendingLimit() != null && !e.code().equals("E_SCHEMA") && !e.code().equals("E_PARSE")) {
                throw in.pendingLimit();
            }
            if (in.pendingDomain() != null && !e.code().equals("E_SCHEMA") && !e.code().equals("E_PARSE")
                    && !e.code().equals("E_LIMIT")) {
                throw in.pendingDomain();
            }
            throw e;
        }
    }

    private static Map<String, Object> header(String caseId, String status) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("schema_version", "1.0");
        r.put("case_id", caseId);
        r.put("status", status);
        return r;
    }

    private static Function<In, Operations.Out> checkEnvelope(Map<?, ?> e) {
        if (!ENVELOPE.containsAll(e.keySet())) {
            throw new QfError("E_SCHEMA", "unknown key in case");
        }
        if (!(e.get("schema_version") instanceof String v) || !SCHEMA_VERSION.matcher(v).matches()) {
            throw new QfError("E_SCHEMA", "bad schema_version", "schema_version");
        }
        if (!(e.get("case_id") instanceof String id) || id.isEmpty()) {
            throw new QfError("E_SCHEMA", "bad case_id", "case_id");
        }
        if (!(e.get("operation") instanceof String name) || !OPERATION.matcher(name).matches()) {
            throw new QfError("E_SCHEMA", "bad operation", "operation");
        }
        if (!(e.get("inputs") instanceof Map<?, ?>)) {
            throw new QfError("E_SCHEMA", "bad inputs", "inputs");
        }
        Function<In, Operations.Out> op = Operations.find(name);
        if (op == null) {
            throw new QfError("E_UNSUPPORTED_OPERATION", "not in this build: " + name, "operation");
        }
        return op;
    }

    private static boolean finite(Object v) {
        return switch (v) {
            case Double d -> Double.isFinite(d);
            case double[] a -> {
                for (double d : a) {
                    if (!Double.isFinite(d)) {
                        yield false;
                    }
                }
                yield true;
            }
            case Object[] a -> allFinite(java.util.Arrays.asList(a));
            case List<?> l -> allFinite(l);
            case Map<?, ?> m -> allFinite(m.values());
            case null, default -> true;
        };
    }

    private static boolean allFinite(Iterable<?> items) {
        for (Object o : items) {
            if (!finite(o)) {
                return false;
            }
        }
        return true;
    }
}
