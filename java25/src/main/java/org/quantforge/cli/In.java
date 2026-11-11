package org.quantforge.cli;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;
import org.quantforge.core.TimeZones;

/** Typed reads of an input object. Anything missing, mistyped or malformed is E_SCHEMA. */
final class In {
    private static final Pattern DATE = Pattern.compile("\\d{4}-\\d{2}-\\d{2}");
    private static final Pattern U64 = Pattern.compile("[0-9]+");
    private static final double MAX_INTEGER = 0x1p53;

    private static final int MAX_ARRAY = 100_000;
    private static final int MAX_MATRIX_ROWS = 200;

    private final Map<?, ?> values;
    /** The first E_LIMIT found, shared with nested objects. Held back so that E_SCHEMA on later inputs wins. */
    private final QfError[] pending;

    private In(Map<?, ?> values, QfError[] pending) {
        this.values = values;
        this.pending = pending;
    }

    /** Wraps a case's inputs and notes any array over the general limit, used by the operation or not. */
    In(Map<?, ?> values) {
        this(values, new QfError[2]);
        scanArrays(values);
    }

    private void scanArrays(Object v) {
        if (v instanceof List<?> l) {
            limit(l.size() > MAX_ARRAY, "array");
            l.forEach(this::scanArrays);
        } else if (v instanceof Map<?, ?> m) {
            m.values().forEach(this::scanArrays);
        }
    }

    /** Notes a limit breach, to be raised once every input has been read. */
    void limit(boolean over, String key) {
        if (over && pending[0] == null) {
            pending[0] = new QfError("E_LIMIT", key + " is above its limit", key);
        }
    }

    /** True if a x b is above max, for values that have both passed their minimum. */
    static boolean productOver(long a, long b, long max) {
        return a > 0 && b > 0 && (double) a * (double) b > max;
    }

    /** Ruling F-1: the exact strings "NaN", "Infinity" and "-Infinity" in a Real field; NaN for anything else. */
    static double nonFiniteToken(Object v) {
        if (!(v instanceof String s)) {
            return Double.NaN;
        }
        return switch (s) {
            case "Infinity" -> Double.POSITIVE_INFINITY;
            case "-Infinity" -> Double.NEGATIVE_INFINITY;
            default -> Double.NaN;
        };
    }

    /** True if v is one of the three non-finite tokens of ruling F-1. */
    static boolean isNonFiniteToken(Object v) {
        return "NaN".equals(v) || "Infinity".equals(v) || "-Infinity".equals(v);
    }

    /** Ruling F-2: the first non-finite Real read, raised after any held E_LIMIT and before every rule check. */
    QfError pendingDomain() {
        return pending[1];
    }

    QfError pendingLimit() {
        return pending[0];
    }

    /** Call once all inputs are read and before any work: raises a held E_LIMIT. */
    void gate() {
        if (pending[0] != null) {
            throw pending[0];
        }
        if (pending[1] != null) {
            throw pending[1];
        }
    }

    /** {@link #gate()} as an expression, for the last input read in an argument list. */
    <T> T gate(T lastInput) {
        gate();
        return lastInput;
    }

    long atMost(String key, long max) {
        long v = integer(key);
        limit(v > max, key);
        return v;
    }

    long atMost(String key, long fallback, long max) {
        return has(key) ? atMost(key, max) : fallback;
    }

    private static QfError schema(String key, String why) {
        return new QfError("E_SCHEMA", key + ": " + why, key);
    }

    boolean has(String key) {
        return values.get(key) != null;
    }

    /** The key is present, even with a null value. */
    boolean hasKey(String key) {
        return values.containsKey(key);
    }

    /** A required key whose value may be null: absent is E_SCHEMA. */
    Double nullableReal(String key) {
        if (!hasKey(key)) {
            throw schema(key, "missing");
        }
        return realOrNull(key);
    }

    /** A required key holding any JSON value, null included. */
    Object anyValue(String key) {
        if (!hasKey(key)) {
            throw schema(key, "missing");
        }
        return values.get(key);
    }

    Map<?, ?> raw() {
        return values;
    }

    private Object need(String key) {
        Object v = values.get(key);
        if (v == null) {
            throw schema(key, "missing");
        }
        return v;
    }

    private double realOf(String key, Object v) {
        if (v instanceof Json.Number n) {
            return n.value();
        }
        double token = nonFiniteToken(v);
        if (!Double.isNaN(token) || "NaN".equals(v)) {
            if (pending[1] == null) {
                pending[1] = new QfError("E_DOMAIN", key + " must be finite", key);
            }
            return token;
        }
        throw schema(key, "expected a number");
    }

    private static long integerOf(String key, Object v) {
        if (v instanceof Json.Number n && n.isIntegerForm() && Math.abs(n.value()) <= MAX_INTEGER) {
            return (long) n.value();
        }
        throw schema(key, "expected an integer");
    }

    double real(String key) {
        return realOf(key, need(key));
    }

    double real(String key, double fallback) {
        return has(key) ? real(key) : fallback;
    }

    Double realOrNull(String key) {
        return has(key) ? real(key) : null;
    }

    long integer(String key) {
        return integerOf(key, need(key));
    }

    long integer(String key, long fallback) {
        return has(key) ? integer(key) : fallback;
    }

    boolean bool(String key) {
        if (need(key) instanceof Boolean b) {
            return b;
        }
        throw schema(key, "expected a boolean");
    }

    boolean bool(String key, boolean fallback) {
        return has(key) ? bool(key) : fallback;
    }

    String string(String key) {
        if (need(key) instanceof String s) {
            return s;
        }
        throw schema(key, "expected a string");
    }

    <E extends Enum<E>> E choice(String key, Class<E> type) {
        return parseEnum(key, string(key), type);
    }

    static <E extends Enum<E>> E parseEnum(String key, String text, Class<E> type) {
        for (E e : type.getEnumConstants()) {
            if (e.name().equals(text)) {
                return e;
            }
        }
        throw schema(key, "not a listed value");
    }

    private static LocalDate dateOf(String key, Object v) {
        if (v instanceof String s && DATE.matcher(s).matches()) {
            try {
                return LocalDate.parse(s);
            } catch (DateTimeParseException e) {
                throw schema(key, "no such date");
            }
        }
        throw schema(key, "expected a date");
    }

    LocalDate date(String key) {
        return dateOf(key, need(key));
    }

    long instant(String key) {
        return TimeZones.parseInstant(string(key));
    }

    List<Long> instants(String key) {
        List<Long> out = new ArrayList<>();
        for (Object v : list(key)) {
            if (!(v instanceof String s)) {
                throw schema(key, "expected instants");
            }
            out.add(TimeZones.parseInstant(s));
        }
        return out;
    }

    long u64(String key) {
        return u64Of(key, need(key));
    }

    private static long u64Of(String key, Object v) {
        if (v instanceof String s && U64.matcher(s).matches()) {
            try {
                return Long.parseUnsignedLong(s);
            } catch (NumberFormatException e) {
                throw schema(key, "does not fit 64 bits");
            }
        }
        throw schema(key, "expected a decimal u64 string");
    }

    private List<?> list(String key) {
        if (need(key) instanceof List<?> l) {
            return l;
        }
        throw schema(key, "expected an array");
    }

    double[] reals(String key) {
        return realsOf(key, list(key));
    }

    private double[] realsOf(String key, List<?> l) {
        double[] out = new double[l.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = realOf(key, l.get(i));
        }
        return out;
    }

    /** An array of reals in which null is allowed. */
    List<Double> nullableReals(String key) {
        List<Double> out = new ArrayList<>();
        for (Object v : list(key)) {
            out.add(v == null ? null : Double.valueOf(realOf(key, v)));
        }
        return out;
    }

    /** An array of integers in which null is allowed. */
    List<Long> nullableIntegers(String key) {
        List<Long> out = new ArrayList<>();
        for (Object v : list(key)) {
            out.add(v == null ? null : Long.valueOf(integerOf(key, v)));
        }
        return out;
    }

    /** Refuses an optional key that is present with a null value (ruling I-12: null only where a rule allows it). */
    void notNull(String key) {
        if (hasKey(key) && values.get(key) == null) {
            throw schema(key, "null is not allowed here");
        }
    }

    double[][] matrix(String key) {
        List<?> rows = list(key);
        limit(rows.size() > MAX_MATRIX_ROWS, key);
        double[][] out = new double[rows.size()][];
        for (int i = 0; i < out.length; i++) {
            if (!(rows.get(i) instanceof List<?> row)) {
                throw schema(key, "expected an array of rows");
            }
            out[i] = realsOf(key, row);
        }
        return out;
    }

    /** A matrix without the row limit of core.linalg. */
    double[][] anyMatrix(String key) {
        List<?> rows = list(key);
        double[][] out = new double[rows.size()][];
        for (int i = 0; i < out.length; i++) {
            if (!(rows.get(i) instanceof List<?> row)) {
                throw schema(key, "expected an array of rows");
            }
            out[i] = realsOf(key, row);
        }
        return out;
    }

    long[] integers(String key) {
        List<?> l = list(key);
        long[] out = new long[l.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = integerOf(key, l.get(i));
        }
        return out;
    }

    List<String> strings(String key) {
        List<String> out = new ArrayList<>();
        for (Object v : list(key)) {
            if (!(v instanceof String s)) {
                throw schema(key, "expected strings");
            }
            out.add(s);
        }
        return out;
    }

    List<LocalDate> dates(String key) {
        List<LocalDate> out = new ArrayList<>();
        for (Object v : list(key)) {
            out.add(dateOf(key, v));
        }
        return out;
    }

    long[] u64s(String key, int size) {
        List<?> l = list(key);
        if (l.size() != size) {
            throw schema(key, "expected " + size + " values");
        }
        long[] out = new long[size];
        for (int i = 0; i < size; i++) {
            out[i] = u64Of(key, l.get(i));
        }
        return out;
    }

    In object(String key) {
        if (need(key) instanceof Map<?, ?> m) {
            return new In(m, pending);
        }
        throw schema(key, "expected an object");
    }

    List<In> objects(String key) {
        List<In> out = new ArrayList<>();
        for (Object v : list(key)) {
            if (!(v instanceof Map<?, ?> m)) {
                throw schema(key, "expected an array of objects");
            }
            out.add(new In(m, pending));
        }
        return out;
    }

    /** Keys of an object input, for maps keyed by data such as instrument ids. */
    Iterable<String> keys() {
        List<String> out = new ArrayList<>();
        for (Object k : values.keySet()) {
            out.add((String) k);
        }
        return out;
    }
}
