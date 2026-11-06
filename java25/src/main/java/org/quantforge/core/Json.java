package org.quantforge.core;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Strict RFC 8259 reader and a small writer. Parsed values are null, Boolean, String, Json.Number, List
 * and Map. Overflowing numbers and lone surrogates are recorded rather than rejected, because callers
 * rank those errors after a parse error found later in the same text.
 */
public final class Json {
    /** A number with its source text, which tells an integer from a real. */
    public record Number(double value, String text) {
        public boolean isIntegerForm() {
            return text.indexOf('.') < 0 && text.indexOf('e') < 0 && text.indexOf('E') < 0;
        }
    }

    public record Document(Object value, boolean numberOverflow, boolean loneSurrogate) {}

    private final String s;
    private int i;
    private boolean overflow;
    private boolean lone;

    private Json(String s) {
        this.s = s;
    }

    /**
     * The lexical depth scan of limits.md B2. It checks no syntax, and callers run it before parsing, which also
     * keeps the recursive parser within its stack.
     */
    public static boolean nestsDeeperThan(String text, int limit) {
        int depth = 0;
        boolean inString = false;
        for (int k = 0; k < text.length(); k++) {
            char c = text.charAt(k);
            if (inString) {
                if (c == '\\') {
                    k++;
                } else if (c == '"') {
                    inString = false;
                }
            } else if (c == '"') {
                inString = true;
            } else if (c == '[' || c == '{') {
                if (++depth > limit) {
                    return true;
                }
            } else if (c == ']' || c == '}') {
                depth--;
            }
        }
        return false;
    }

    /** Parses a whole document. Callers run {@link #nestsDeeperThan} first. Throws E_PARSE on bad JSON or a duplicate key at any depth. */
    public static Document parse(String text) {
        Json p = new Json(text);
        p.ws();
        Object v = p.value();
        p.ws();
        if (p.i != text.length()) {
            throw p.bad("trailing text");
        }
        return new Document(v, p.overflow, p.lone);
    }

    private QfError bad(String why) {
        return new QfError("E_PARSE", why + " at offset " + i);
    }

    private void ws() {
        while (i < s.length()) {
            char c = s.charAt(i);
            if (c != ' ' && c != '\t' && c != '\n' && c != '\r') {
                return;
            }
            i++;
        }
    }

    private char peek() {
        if (i >= s.length()) {
            throw bad("unexpected end");
        }
        return s.charAt(i);
    }

    private Object value() {
        return switch (peek()) {
            case '{' -> object();
            case '[' -> array();
            case '"' -> string();
            case 't' -> literal("true", Boolean.TRUE);
            case 'f' -> literal("false", Boolean.FALSE);
            case 'n' -> literal("null", null);
            default -> number();
        };
    }

    private Object literal(String word, Object v) {
        if (!s.startsWith(word, i)) {
            throw bad("bad literal");
        }
        i += word.length();
        return v;
    }

    private Map<String, Object> object() {
        Map<String, Object> m = new LinkedHashMap<>();
        i++;
        ws();
        if (peek() == '}') {
            i++;
            return m;
        }
        while (true) {
            ws();
            if (peek() != '"') {
                throw bad("expected key");
            }
            String k = string();
            ws();
            if (peek() != ':') {
                throw bad("expected colon");
            }
            i++;
            ws();
            Object v = value();
            if (m.containsKey(k)) {
                throw bad("duplicate key");
            }
            m.put(k, v);
            ws();
            char c = peek();
            if (c != '}' && c != ',') {
                throw bad("expected comma");
            }
            i++;
            if (c == '}') {
                return m;
            }
        }
    }

    private List<Object> array() {
        List<Object> a = new ArrayList<>();
        i++;
        ws();
        if (peek() == ']') {
            i++;
            return a;
        }
        while (true) {
            ws();
            a.add(value());
            ws();
            char c = peek();
            if (c != ']' && c != ',') {
                throw bad("expected comma");
            }
            i++;
            if (c == ']') {
                return a;
            }
        }
    }

    private String string() {
        StringBuilder b = new StringBuilder();
        i++;
        while (true) {
            char c = peek();
            if (c < 0x20) {
                throw bad("control character in string");
            }
            i++;
            if (c == '"') {
                break;
            }
            if (c != '\\') {
                b.append(c);
                continue;
            }
            char e = peek();
            i++;
            switch (e) {
                case '"', '\\', '/' -> b.append(e);
                case 'b' -> b.append('\b');
                case 'f' -> b.append('\f');
                case 'n' -> b.append('\n');
                case 'r' -> b.append('\r');
                case 't' -> b.append('\t');
                case 'u' -> b.append(hex4());
                default -> throw bad("bad escape");
            }
        }
        noteSurrogates(b);
        return b.toString();
    }

    private char hex4() {
        if (i + 4 > s.length()) {
            throw bad("short unicode escape");
        }
        int v = 0;
        for (int k = 0; k < 4; k++) {
            char c = s.charAt(i + k);
            int d = c < 128 ? Character.digit(c, 16) : -1;
            if (d < 0) {
                throw bad("bad unicode escape");
            }
            v = v * 16 + d;
        }
        i += 4;
        return (char) v;
    }

    private void noteSurrogates(CharSequence t) {
        for (int k = 0; k < t.length(); k++) {
            char c = t.charAt(k);
            if (Character.isHighSurrogate(c) && k + 1 < t.length() && Character.isLowSurrogate(t.charAt(k + 1))) {
                k++;
            } else if (Character.isSurrogate(c)) {
                lone = true;
            }
        }
    }

    private boolean digitAt(int k) {
        return k < s.length() && s.charAt(k) >= '0' && s.charAt(k) <= '9';
    }

    private int digits(int k) {
        if (!digitAt(k)) {
            i = k;
            throw bad("expected digit");
        }
        while (digitAt(k)) {
            k++;
        }
        return k;
    }

    private Number number() {
        int start = i;
        int k = i;
        if (s.charAt(k) == '-') {
            k++;
        }
        if (k < s.length() && s.charAt(k) == '0') {
            k++;
        } else {
            k = digits(k);
        }
        if (k < s.length() && s.charAt(k) == '.') {
            k = digits(k + 1);
        }
        if (k < s.length() && (s.charAt(k) == 'e' || s.charAt(k) == 'E')) {
            k++;
            if (k < s.length() && (s.charAt(k) == '+' || s.charAt(k) == '-')) {
                k++;
            }
            k = digits(k);
        }
        i = k;
        String text = s.substring(start, k);
        double v = Double.parseDouble(text);
        if (Double.isInfinite(v)) {
            overflow = true;
        }
        return new Number(v, text);
    }

    /** Levels of nesting in a parsed value. An object or array is one level; scalars add none. */
    public static int depth(Object v) {
        int inner = 0;
        switch (v) {
            case List<?> l -> {
                for (Object e : l) {
                    inner = Math.max(inner, depth(e));
                }
                return inner + 1;
            }
            case Map<?, ?> m -> {
                for (Object e : m.values()) {
                    inner = Math.max(inner, depth(e));
                }
                return inner + 1;
            }
            case null, default -> {
                return 0;
            }
        }
    }

    /** True if any string or key in a parsed value holds a lone surrogate. */
    public static boolean hasLoneSurrogate(Object v) {
        switch (v) {
            case String s -> {
                Json j = new Json(s);
                j.noteSurrogates(s);
                return j.lone;
            }
            case List<?> l -> {
                return l.stream().anyMatch(Json::hasLoneSurrogate);
            }
            case Map<?, ?> m -> {
                return m.keySet().stream().anyMatch(Json::hasLoneSurrogate)
                        || m.values().stream().anyMatch(Json::hasLoneSurrogate);
            }
            case null, default -> {
                return false;
            }
        }
    }

    /** Writes a value as JSON. Accepts maps, lists, strings, booleans, boxed numbers and numeric arrays. */
    public static void write(StringBuilder b, Object v) {
        switch (v) {
            case null -> b.append("null");
            case Boolean x -> b.append(x.booleanValue());
            case Integer x -> b.append(x.intValue());
            case Long x -> b.append(x.longValue());
            case Double x -> writeDouble(b, x);
            case Number x -> b.append(x.text());
            case String x -> writeString(b, x);
            case double[] x -> {
                b.append('[');
                for (int k = 0; k < x.length; k++) {
                    if (k > 0) {
                        b.append(',');
                    }
                    writeDouble(b, x[k]);
                }
                b.append(']');
            }
            case Object[] x -> write(b, Arrays.asList(x));
            case List<?> x -> {
                b.append('[');
                boolean first = true;
                for (Object e : x) {
                    if (!first) {
                        b.append(',');
                    }
                    first = false;
                    write(b, e);
                }
                b.append(']');
            }
            case Map<?, ?> x -> {
                b.append('{');
                boolean first = true;
                for (Map.Entry<?, ?> e : x.entrySet()) {
                    if (!first) {
                        b.append(',');
                    }
                    first = false;
                    writeString(b, (String) e.getKey());
                    b.append(':');
                    write(b, e.getValue());
                }
                b.append('}');
            }
            default -> throw new IllegalArgumentException("cannot write " + v.getClass());
        }
    }

    private static void writeDouble(StringBuilder b, double d) {
        if (Double.isNaN(d) || Double.isInfinite(d)) {
            b.append("null");
        } else {
            b.append(d); // Shortest form that reads back to the same binary64.
        }
    }

    private static void writeString(StringBuilder b, String t) {
        b.append('"');
        for (int k = 0; k < t.length(); k++) {
            char c = t.charAt(k);
            if (c == '"' || c == '\\') {
                b.append('\\').append(c);
            } else if (c < 0x20) {
                b.append(String.format("\\u%04x", (int) c));
            } else if (Character.isHighSurrogate(c) && k + 1 < t.length() && Character.isLowSurrogate(t.charAt(k + 1))) {
                b.append(c).append(t.charAt(++k));
            } else if (Character.isSurrogate(c)) {
                b.append(String.format("\\u%04x", (int) c)); // Cannot be encoded as UTF-8.
            } else {
                b.append(c);
            }
        }
        b.append('"');
    }
}
