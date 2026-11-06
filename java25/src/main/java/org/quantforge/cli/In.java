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

    private final Map<?, ?> values;

    In(Map<?, ?> values) {
        this.values = values;
    }

    private static QfError schema(String key, String why) {
        return new QfError("E_SCHEMA", key + ": " + why, key);
    }

    boolean has(String key) {
        return values.get(key) != null;
    }

    private Object need(String key) {
        Object v = values.get(key);
        if (v == null) {
            throw schema(key, "missing");
        }
        return v;
    }

    private static double realOf(String key, Object v) {
        if (v instanceof Json.Number n) {
            return n.value();
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

    private static double[] realsOf(String key, List<?> l) {
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

    double[][] matrix(String key) {
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
            return new In(m);
        }
        throw schema(key, "expected an object");
    }

    List<In> objects(String key) {
        List<In> out = new ArrayList<>();
        for (Object v : list(key)) {
            if (!(v instanceof Map<?, ?> m)) {
                throw schema(key, "expected an array of objects");
            }
            out.add(new In(m));
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
