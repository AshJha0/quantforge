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

    private static final String CONTRACT = "1.0.0";
    private static final String VERSION = "0.3.0";
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
        if (args.length != 1) {
            System.err.println("usage: quantforge run|batch|version|operations");
            return 64;
        }
        switch (args[0]) {
            case "run" -> {
                Reply r = handle(decode(in.readAllBytes()));
                write(out, r.json());
                return r.ok() ? 0 : 2;
            }
            case "batch" -> {
                batch(in, out);
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

    private static void batch(InputStream raw, OutputStream out) throws IOException {
        BufferedInputStream in = new BufferedInputStream(raw);
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        int b;
        while ((b = in.read()) >= 0) {
            if (b == '\n') {
                write(out, handle(decode(line.toByteArray())).json());
                line.reset();
            } else {
                line.write(b);
            }
        }
        if (line.size() > 0) {
            write(out, handle(decode(line.toByteArray())).json());
        }
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
            r.put("diagnostics", result.diagnostics());
            return new Reply(json(r), true);
        } catch (QfError e) {
            Map<String, Object> err = new LinkedHashMap<>();
            err.put("code", e.code());
            err.put("message", String.valueOf(e.getMessage()));
            if (e.field() != null) {
                err.put("field", e.field());
            }
            Map<String, Object> r = header(caseId, "error");
            r.put("error", err);
            return new Reply(json(r), false);
        }
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
