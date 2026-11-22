package org.quantforge.paper;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.regex.Pattern;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;
import org.quantforge.micro.DarkPool;
import org.quantforge.micro.LitMatching;
import org.quantforge.micro.Sor;

/**
 * Paper trading ({@code specifications/10-execution/paper-trading.md}, rulings HR-42 to HR-55): hash-chained
 * ledger, book (positions, cash, financing), daily P&amp;L explain, pre-trade checks and the simulated session.
 * A port of the Python reference ({@code paper.py}, {@code paper_fills.py}).
 *
 * <p>Nothing here opens a socket or names an order-entry endpoint: no live order can be placed (HR-42). A
 * {@code mode} other than {@code "simulated"} is {@code E_UNSUPPORTED_OPERATION}.
 *
 * <p>Decimal arithmetic is exact and range-checked (HR-77): out of range is E_LIMIT, never a rounded value; the
 * only divisions are the average cost (half-even, 18 decimals), interest and borrow (half-even, 0.01) and the mid. Ledger bytes are those of Python
 * {@code json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True)} (HR-45).
 */
public final class Paper {
    private Paper() {}

    public static final String LABEL = "crypto venue; simulated";
    public static final String CEILING =
            "Paper trading on free data; simulated fills; no evidence of tradable profitability.";
    public static final String GENESIS = "0".repeat(64);
    static final List<String> KINDS = List.of("ORDER", "REJECT", "FILL", "CANCEL", "EOD", "TCA");
    static final List<String> TYPES =
            List.of("LIMIT", "MARKET", "IOC", "FOK", "ICEBERG", "POST_ONLY", "PEG_MID", "PEG_PRIMARY");
    static final List<String> REASONS = List.of("KILL_SWITCH", "MAX_ORDERS", "MAX_QTY", "PRICE_BAND",
            "MAX_NOTIONAL", "MAX_POSITION", "NO_SHORT", "INSUFFICIENT_CASH");
    static final List<String> VENUES = List.of("LIT", "DARK", "SOR");
    static final String TRADER = "PAPER";
    private static final String SYM = "S";

    /** The 200-digit context of the Python reference (HR-58): no in-range sum, difference or product rounds. */
    static final MathContext MC = new MathContext(200, RoundingMode.HALF_EVEN);
    static final int MAX_DIGITS = 36;
    static final int MAX_SCALE = 36;
    static final int MAX_INPUT_SCALE = 18;

    /** HR-57/HR-77: {@code x} unchanged if in range (36 digits, {@code maxScale} decimals), else E_LIMIT; never rounded. */
    static BigDecimal rng(BigDecimal x, String path, int maxScale) {
        if (x.signum() == 0) {
            return x;
        }
        BigDecimal n = x.stripTrailingZeros();
        int scale = Math.max(n.scale(), 0);
        int digits = n.scale() >= 0 ? n.precision() : n.precision() - n.scale();
        if (digits > MAX_DIGITS || scale > maxScale) {
            throw new QfError("E_LIMIT", path + ": decimal outside the exact range (36 digits, " + maxScale
                    + " decimals; HR-57)", path);
        }
        return x;
    }

    static BigDecimal rng(BigDecimal x, String path) {
        return rng(x, path, MAX_SCALE);
    }

    // ------------------------------------------------------------------ decimals (HR-44)

    private static final Pattern FINITE = Pattern.compile("[+-]?(\\d+(\\.\\d*)?|\\.\\d+)([eE][+-]?\\d+)?");
    private static final Pattern NON_FINITE =
            Pattern.compile("(?i)[+-]?(inf|infinity|nan\\d*|snan\\d*)");

    /** Python {@code Decimal(text)}: a non-finite token (HR-12, F-2a) and anything else malformed (KR-344) are E_SCHEMA. */
    static BigDecimal parse(String text, String name) {
        String t = text.strip();
        if (FINITE.matcher(t).matches()) {
            try {
                return new BigDecimal(t);
            } catch (NumberFormatException | ArithmeticException e) {
                throw new QfError("E_SCHEMA", name + " is not a decimal", name);
            }
        }
        if (NON_FINITE.matcher(t).matches()) {
            throw new QfError("E_SCHEMA", name + " is not a finite decimal", name);
        }
        throw new QfError("E_SCHEMA", name + " is not a decimal", name);
    }

    /** Python {@code dec}: a decimal given as a string or an integer; reals and booleans are refused (E_INPUT). */
    static BigDecimal dec(Object v, String name) {
        switch (v) {
            case BigDecimal b -> {
                return rng(b, name);
            }
            case Boolean b -> throw new QfError("E_INPUT", name + " must be a decimal string", name);
            case Json.Number n -> {
                if (!n.isIntegerForm()) {
                    throw new QfError("E_INPUT", name + " must be a decimal string", name);
                }
                return rng(new BigDecimal(new BigInteger(n.text())), name);
            }
            case Long l -> {
                return rng(BigDecimal.valueOf(l), name);
            }
            case Integer l -> {
                return rng(BigDecimal.valueOf(l), name);
            }
            case String s -> {
                return rng(parse(s, name), name);
            }
            case null, default -> throw new QfError("E_SCHEMA", name + " is not a decimal", name);
        }
    }

    /** A decimal input over the CLI: a JSON string (HR-12, HR-44), at most 36 digits and 18 decimals (HR-77). */
    static BigDecimal dstr(Object v, String name) {
        if (!(v instanceof String s)) {
            throw new QfError("E_SCHEMA", name + " must be a decimal string", name);
        }
        return rng(rng(parse(s, name), name), name, MAX_INPUT_SCALE);
    }

    /**
     * The E_SCHEMA part of {@link #dstr} alone (KR-344, HR-66): a JSON string that parses as a finite decimal,
     * checked for every decimal of a case before any range (E_LIMIT) check.
     */
    static void schemaDec(Object v, String name) {
        if (!(v instanceof String s)) {
            throw new QfError("E_SCHEMA", name + " must be a decimal string", name);
        }
        parse(s, name);
    }

    /** No exponent, no trailing zeros, "0" for zero (HR-12). */
    public static String fmt(BigDecimal x) {
        return LitMatching.fmt(x);
    }

    static BigDecimal add(BigDecimal a, BigDecimal b) {
        return a.add(b, MC);
    }

    static BigDecimal sub(BigDecimal a, BigDecimal b) {
        return a.subtract(b, MC);
    }

    static BigDecimal mul(BigDecimal a, BigDecimal b) {
        return a.multiply(b, MC);
    }

    static BigDecimal div(BigDecimal a, BigDecimal b) {
        return a.divide(b, MC);
    }

    static BigDecimal of(long v) {
        return BigDecimal.valueOf(v);
    }

    /**
     * +1 BUY, -1 SELL. A present side that is not a JSON string is mistyped, E_SCHEMA (cli-contract.md, error
     * table; fuzz run 44937631714); a string that is not listed is E_INPUT (paper-trading.md, Errors; rule_h-0040).
     */
    static int sideSign(Object side) {
        if (side != null && !(side instanceof String)) {
            throw new QfError("E_SCHEMA", "side must be a string", "side");
        }
        if ("BUY".equals(side)) {
            return 1;
        }
        if ("SELL".equals(side)) {
            return -1;
        }
        throw new QfError("E_INPUT", "unknown side " + side, "side");
    }

    // ------------------------------------------------------------------ shortest round trip (TCA, cli-contract.md)

    /**
     * The decimal value of Python {@code repr(x)}: the fewest significant digits that read back to {@code x}, and
     * of those the one nearest {@code x} (ties to an even last digit). Exact search over BigDecimal, so it does not
     * rely on the formatting of {@code Double.toString}.
     */
    public static BigDecimal shortest(double x) {
        if (x == 0.0) {
            return BigDecimal.ZERO;
        }
        BigDecimal exact = new BigDecimal(x);
        for (int n = 1; n <= 17; n++) {
            BigDecimal lo = exact.round(new MathContext(n, RoundingMode.DOWN));
            BigDecimal hi = exact.round(new MathContext(n, RoundingMode.UP));
            boolean okLo = Double.parseDouble(lo.toString()) == x;
            boolean okHi = Double.parseDouble(hi.toString()) == x;
            if (okLo && okHi) {
                int c = exact.subtract(lo).abs().compareTo(hi.subtract(exact).abs());
                if (c != 0) {
                    return c < 0 ? lo : hi;
                }
                return lo.unscaledValue().testBit(0) ? hi : lo;
            }
            if (okLo) {
                return lo;
            }
            if (okHi) {
                return hi;
            }
        }
        throw new IllegalStateException("no round-trip decimal for " + x); // 17 digits always suffice
    }

    /** {@code fmt(Decimal(repr(x)))} of the Python reference. */
    public static String fmtDouble(double x) {
        if (Double.isNaN(x)) {
            return "NaN";
        }
        if (Double.isInfinite(x)) {
            return x > 0 ? "Infinity" : "-Infinity";
        }
        return fmt(shortest(x));
    }

    /** Python {@code float(Decimal)}: the binary64 nearest the decimal. */
    static double toDouble(BigDecimal d) {
        return Double.parseDouble(d.toString());
    }

    // ------------------------------------------------------------------ canonical bytes and hash (HR-45)

    /** Python's sort order for str keys: by code point. */
    static final Comparator<String> CODE_POINT = (a, b) -> {
        int i = 0;
        int j = 0;
        while (i < a.length() && j < b.length()) {
            int ca = a.codePointAt(i);
            int cb = b.codePointAt(j);
            if (ca != cb) {
                return Integer.compare(ca, cb);
            }
            i += Character.charCount(ca);
            j += Character.charCount(cb);
        }
        return Integer.compare(a.length() - i, b.length() - j);
    };

    private static void check(Object v, String path) {
        switch (v) {
            case Map<?, ?> m -> {
                for (var e : m.entrySet()) {
                    check(e.getValue(), path + "." + e.getKey());
                }
            }
            case List<?> l -> {
                for (int k = 0; k < l.size(); k++) {
                    check(l.get(k), path + "[" + k + "]");
                }
            }
            case Boolean b -> throw new QfError("E_INPUT", path + " must be a string (only seq is an integer)", path);
            case Json.Number n -> {
                if (!n.isIntegerForm() || !path.equals(".seq")) {
                    throw new QfError("E_INPUT", path + " must be a string (only seq is an integer)", path);
                }
            }
            case Long l -> {
                if (!path.equals(".seq")) {
                    throw new QfError("E_INPUT", path + " must be a string (only seq is an integer)", path);
                }
            }
            case Integer l -> {
                if (!path.equals(".seq")) {
                    throw new QfError("E_INPUT", path + " must be a string (only seq is an integer)", path);
                }
            }
            case String s -> {}
            case null -> {}
            default -> throw new QfError("E_INPUT", path + " must be a string", path);
        }
    }

    /** Python json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True) of a value. */
    public static void writeCanonical(StringBuilder b, Object v) {
        switch (v) {
            case null -> b.append("null");
            case Boolean x -> b.append(x ? "true" : "false");
            case Long x -> b.append(x.longValue());
            case Integer x -> b.append(x.intValue());
            case Json.Number x -> b.append(new BigInteger(x.text()));
            case String s -> writeString(b, s);
            case List<?> l -> {
                b.append('[');
                for (int k = 0; k < l.size(); k++) {
                    if (k > 0) {
                        b.append(',');
                    }
                    writeCanonical(b, l.get(k));
                }
                b.append(']');
            }
            case Map<?, ?> m -> {
                List<String> keys = new ArrayList<>();
                for (Object k : m.keySet()) {
                    keys.add((String) k);
                }
                keys.sort(CODE_POINT);
                b.append('{');
                boolean first = true;
                for (String k : keys) {
                    if (!first) {
                        b.append(',');
                    }
                    first = false;
                    writeString(b, k);
                    b.append(':');
                    writeCanonical(b, m.get(k));
                }
                b.append('}');
            }
            default -> throw new QfError("E_INPUT", "cannot serialise " + v.getClass().getSimpleName(), "body");
        }
    }

    private static final char[] HEX = "0123456789abcdef".toCharArray();

    private static void writeString(StringBuilder b, String t) {
        b.append('"');
        for (int k = 0; k < t.length(); k++) {
            char c = t.charAt(k);
            switch (c) {
                case '"' -> b.append("\\\"");
                case '\\' -> b.append("\\\\");
                case '\n' -> b.append("\\n");
                case '\r' -> b.append("\\r");
                case '\t' -> b.append("\\t");
                case '\b' -> b.append("\\b");
                case '\f' -> b.append("\\f");
                default -> {
                    if (c < 0x20 || c > 0x7e) {
                        b.append("\\u").append(HEX[(c >> 12) & 15]).append(HEX[(c >> 8) & 15])
                                .append(HEX[(c >> 4) & 15]).append(HEX[c & 15]);
                    } else {
                        b.append(c);
                    }
                }
            }
        }
        b.append('"');
    }

    /** Canonical bytes of a record without its hash (HR-45), as an ASCII string. */
    public static String canonical(Map<?, ?> record) {
        Map<Object, Object> body = new LinkedHashMap<>();
        for (var e : record.entrySet()) {
            if (!"hash".equals(e.getKey())) {
                body.put(e.getKey(), e.getValue());
            }
        }
        check(body, "");
        StringBuilder b = new StringBuilder();
        writeCanonical(b, body);
        return b.toString();
    }

    public static String sha256(String ascii) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(md.digest(ascii.getBytes(StandardCharsets.US_ASCII)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    /** Append-only hash-chained ledger held as JSON Lines text. */
    public static final class Ledger {
        final List<String> lines = new ArrayList<>();
        final List<Map<String, Object>> records = new ArrayList<>();
        String head = GENESIS;

        public Map<String, Object> append(String kind, String ts, Map<String, Object> body) {
            if (!KINDS.contains(kind)) {
                throw new QfError("E_INPUT", "unknown kind " + kind, "kind");
            }
            Map<String, Object> rec = new TreeMap<>(CODE_POINT);
            rec.put("seq", (long) lines.size());
            rec.put("ts", ts);
            rec.put("kind", kind);
            rec.put("label", LABEL);
            rec.put("body", body);
            rec.put("prev", head);
            String h = sha256(canonical(rec));
            rec.put("hash", h);
            StringBuilder b = new StringBuilder();
            writeCanonical(b, rec);
            lines.add(b.toString());
            records.add(rec);
            head = h;
            return rec;
        }

        public String text() {
            StringBuilder b = new StringBuilder();
            for (String l : lines) {
                b.append(l).append('\n');
            }
            return b.toString();
        }

        public String head() {
            return head;
        }

        public List<Map<String, Object>> records() {
            return records;
        }
    }

    /** Python {@code str.splitlines}. */
    static List<String> splitLines(String text) {
        List<String> out = new ArrayList<>();
        int start = 0;
        int n = text.length();
        for (int k = 0; k < n; k++) {
            char c = text.charAt(k);
            if (c == '\n' || c == '\r' || c == '\u000b' || c == '\u000c' || c == '\u001c' || c == '\u001d'
                    || c == '\u001e' || c == '\u0085' || c == ' ' || c == ' ') {
                out.add(text.substring(start, k));
                if (c == '\r' && k + 1 < n && text.charAt(k + 1) == '\n') {
                    k++;
                }
                start = k + 1;
            }
        }
        if (start < n) {
            out.add(text.substring(start));
        }
        return out;
    }

    /** {@code paper.ledger.verify}: never repairs; reports the first bad record. */
    public static Map<String, Object> verify(String text) {
        String prev = GENESIS;
        List<String> lines = splitLines(text);
        for (int n = 0; n < lines.size(); n++) {
            String line = lines.get(n);
            Map<?, ?> rec;
            Object stored;
            String computed;
            try {
                if (Json.nestsDeeperThan(line, 500)) {
                    return bad(n, "PARSE");
                }
                if (!(Json.parse(line).value() instanceof Map<?, ?> m) || !m.containsKey("hash")) {
                    return bad(n, "PARSE");
                }
                rec = m;
                stored = m.get("hash");
                computed = sha256(canonical(m));
            } catch (RuntimeException e) {
                return bad(n, "PARSE");
            }
            if (!(rec.get("seq") instanceof Json.Number s && s.isIntegerForm()
                    && new BigInteger(s.text()).equals(BigInteger.valueOf(n)))) {
                return bad(n, "SEQ");
            }
            if (!computed.equals(stored)) {
                return bad(n, "HASH");
            }
            if (!prev.equals(rec.get("prev"))) {
                return bad(n, "LINK");
            }
            if (!LABEL.equals(rec.get("label"))) {
                return bad(n, "LABEL");
            }
            prev = computed;
        }
        Map<String, Object> out = new TreeMap<>();
        out.put("ok", true);
        out.put("records", (long) lines.size());
        out.put("first_bad_seq", null);
        out.put("reason", null);
        out.put("head", prev);
        out.put("label", LABEL);
        return out;
    }

    private static Map<String, Object> bad(int n, String reason) {
        Map<String, Object> out = new TreeMap<>();
        out.put("ok", false);
        out.put("records", (long) n);
        out.put("first_bad_seq", (long) n);
        out.put("reason", reason);
        out.put("head", null);
        out.put("label", LABEL);
        return out;
    }

    private static final List<String> NON_FINITE_TOKENS = List.of("NaN", "Infinity", "-Infinity");

    private static void noNonFinite(Object v, String path) {
        if (v instanceof Map<?, ?> m) {
            for (var e : m.entrySet()) {
                noNonFinite(e.getValue(), path + "/" + e.getKey());
            }
        } else if (v instanceof List<?> l) {
            for (int i = 0; i < l.size(); i++) {
                noNonFinite(l.get(i), path + "/" + i);
            }
        } else if (v instanceof String s && NON_FINITE_TOKENS.contains(s)) {
            throw new QfError("E_SCHEMA", path + " is not a finite decimal", path);
        }
    }

    /** {@code paper.ledger.append} for one record: canonical bytes (HR-45), hash and the full record. */
    public static Map<String, Object> ledgerAppend(long seq, String ts, String kind, Map<?, ?> body, String prev) {
        if (!KINDS.contains(kind)) {
            throw new QfError("E_INPUT", "unknown kind " + kind, "kind");
        }
        if (seq < 0) {
            throw new QfError("E_DOMAIN", "seq must be >= 0", "seq");
        }
        noNonFinite(body, "body");
        Map<String, Object> rec = new TreeMap<>(CODE_POINT);
        rec.put("seq", seq);
        rec.put("ts", ts);
        rec.put("kind", kind);
        rec.put("label", LABEL);
        rec.put("body", body);
        rec.put("prev", prev);
        String raw = canonical(rec);
        String h = sha256(raw);
        rec.put("hash", h);
        Map<String, Object> out = new TreeMap<>();
        out.put("canonical_bytes", raw);
        out.put("hash", h);
        out.put("record", rec);
        out.put("label", LABEL);
        return out;
    }

    // ------------------------------------------------------------------ book (HR-50, HR-52, HR-53)

    static final class Position {
        BigDecimal n = BigDecimal.ZERO;
        BigDecimal c = BigDecimal.ZERO;
    }

    static final class Book {
        BigDecimal cash;
        final Map<String, Position> positions = new LinkedHashMap<>();
        BigDecimal realised = BigDecimal.ZERO;
        BigDecimal fees = BigDecimal.ZERO;

        Book(BigDecimal cash) {
            this.cash = cash;
        }

        Position pos(String symbol) {
            return positions.computeIfAbsent(symbol, k -> new Position());
        }

        /** {@code paper.book.apply_fill}, average cost (HR-50). */
        void applyFill(String symbol, Object side, BigDecimal q, BigDecimal p, BigDecimal f) {
            int s = sideSign(side);
            if (q.signum() <= 0 || p.signum() <= 0) {
                throw new QfError("E_DOMAIN", "quantity and price must be positive", "quantity");
            }
            BigDecimal notional = rng(mul(q, p), "notional");
            cash = rng(sub(cash, rng(add(mul(of(s), notional), f), "cash_flow")), "cash");
            fees = rng(add(fees, f), "fees");
            Position pos = pos(symbol);
            if (pos.n.signum() == 0 || (pos.n.signum() > 0) == (s > 0)) {
                BigDecimal absN = pos.n.abs(MC);
                BigDecimal basis = rng(add(rng(mul(absN, pos.c), "basis"), notional), "basis");
                // HR-77: the one division of the book, rounded half-even to 18 decimals
                pos.c = rng(div(basis, rng(add(absN, q), "position")).setScale(MAX_INPUT_SCALE,
                        RoundingMode.HALF_EVEN), "avg_cost");
                pos.n = rng(add(pos.n, mul(of(s), q)), "position");
                return;
            }
            BigDecimal absN = pos.n.abs(MC);
            BigDecimal closed = q.compareTo(absN) <= 0 ? q : absN;
            int sign = pos.n.signum() > 0 ? 1 : -1;
            realised = rng(add(realised, rng(mul(mul(closed, rng(sub(p, pos.c), "pnl")), of(sign)), "pnl")),
                    "realised");
            pos.n = rng(add(pos.n, mul(of(s), q)), "position");
            if (pos.n.signum() == 0) {
                pos.c = BigDecimal.ZERO;
            } else if ((pos.n.signum() > 0) != (sign > 0)) {
                pos.c = p;
            }
        }

        BigDecimal nav(Map<?, ?> marks) {
            BigDecimal sum = BigDecimal.ZERO;
            for (var e : positions.entrySet()) {
                if (e.getValue().n.signum() != 0) {
                    sum = add(sum, rng(mul(e.getValue().n, dec(mark(marks, e.getKey()), "marks." + e.getKey())),
                            "market_value"));
                }
            }
            return rng(add(cash, sum), "nav");
        }
    }

    private static Object mark(Map<?, ?> marks, String symbol) {
        if (!marks.containsKey(symbol)) {
            throw new QfError("E_SCHEMA", "no mark for " + symbol, "marks");
        }
        return marks.get(symbol);
    }

    record Financing(BigDecimal interest, BigDecimal borrow, BigDecimal financing) {}

    private static final BigDecimal DAYS_PER_YEAR = of(365);

    /** Interest on opening cash and borrow on opening short market value, ACT/365 (HR-52). */
    static Financing financing(BigDecimal cash, List<Object[]> shortsOpen, long days, Object cashRate,
            Object debitRate, Object borrowRate) {
        if (days < 0) {
            throw new QfError("E_DOMAIN", "days must be >= 0", "days");
        }
        BigDecimal r = cash.signum() >= 0 ? dec(cashRate, "cash_rate") : dec(debitRate, "debit_rate");
        BigDecimal d = of(days);
        BigDecimal interest = div(rng(mul(mul(cash, r), d), "interest"), DAYS_PER_YEAR)
                .setScale(2, RoundingMode.HALF_EVEN);
        BigDecimal smv = BigDecimal.ZERO;
        for (Object[] sp : shortsOpen) {
            BigDecimal n = dec(sp[0], "n");
            if (n.signum() < 0) {
                smv = add(smv, mul(n.negate(MC), dec(sp[1], "close")));
            }
        }
        smv = rng(smv, "short_value");
        BigDecimal borrow = div(rng(mul(mul(smv, dec(borrowRate, "borrow_rate")), d), "borrow"), DAYS_PER_YEAR)
                .setScale(2, RoundingMode.HALF_EVEN).negate();
        return new Financing(interest, borrow, rng(add(interest, borrow), "financing"));
    }

    record DayFill(String symbol, Object side, BigDecimal quantity, BigDecimal price, BigDecimal fee) {}

    record Explain(BigDecimal market, BigDecimal trading, BigDecimal fees, Financing fin, BigDecimal total,
            BigDecimal nav) {
        Map<String, Object> body() {
            Map<String, Object> m = new TreeMap<>();
            m.put("market", fmt(market));
            m.put("trading", fmt(trading));
            m.put("fees", fmt(fees));
            m.put("financing", fmt(fin.financing()));
            m.put("interest", fmt(fin.interest()));
            m.put("borrow", fmt(fin.borrow()));
            m.put("total", fmt(total));
            m.put("nav", fmt(nav));
            m.put("label", LABEL);
            m.put("ceiling", CEILING);
            return m;
        }
    }

    /** {@code paper.book.end_of_day} with the explain; total equals the NAV change exactly (HR-53). */
    static Explain endOfDay(Book book, List<DayFill> fills, Map<?, ?> prevMarks, Map<?, ?> marks, long days,
            Object cashRate, Object debitRate, Object borrowRate) {
        Map<String, BigDecimal> opening = new LinkedHashMap<>();
        for (var e : book.positions.entrySet()) {
            if (e.getValue().n.signum() != 0) {
                opening.put(e.getKey(), e.getValue().n);
            }
        }
        BigDecimal nav0 = opening.isEmpty() ? book.cash : book.nav(prevMarks);
        List<Object[]> shorts = new ArrayList<>();
        for (var e : opening.entrySet()) {
            shorts.add(new Object[] {e.getValue(), mark(prevMarks, e.getKey())});
        }
        Financing fin = financing(book.cash, shorts, days, cashRate, debitRate, borrowRate);
        BigDecimal market = BigDecimal.ZERO;
        for (var e : opening.entrySet()) {
            BigDecimal diff = sub(dec(mark(marks, e.getKey()), "mark"), dec(mark(prevMarks, e.getKey()), "prev_mark"));
            market = add(market, mul(e.getValue(), diff));
        }
        BigDecimal trading = BigDecimal.ZERO;
        BigDecimal fees = BigDecimal.ZERO;
        for (DayFill f : fills) {
            int sgn = sideSign(f.side());
            trading = add(trading, mul(mul(of(sgn), f.quantity()), sub(dec(mark(marks, f.symbol()), "mark"), f.price())));
            fees = sub(fees, f.fee());
            book.applyFill(f.symbol(), f.side(), f.quantity(), f.price(), f.fee());
        }
        book.cash = add(book.cash, fin.financing());
        market = rng(market, "market");
        trading = rng(trading, "trading");
        fees = rng(fees, "fees");
        book.cash = rng(book.cash, "cash");
        BigDecimal total = rng(add(add(add(market, trading), fees), fin.financing()), "total");
        BigDecimal nav1 = book.nav(marks);
        if (total.compareTo(sub(nav1, nav0)) != 0) {
            throw new IllegalStateException("explain residual " + sub(sub(nav1, nav0), total)); // HR-53: a defect
        }
        return new Explain(market, trading, fees, fin, total, nav1);
    }

    // ------------------------------------------------------------------ pre-trade checks (HR-42, HR-49)

    private static Object need(Map<?, ?> m, String key, String where) {
        if (!m.containsKey(key)) {
            throw new QfError("E_SCHEMA", where + key + " is missing", where + key);
        }
        return m.get(key);
    }

    /** Python truthiness of a JSON value. */
    static boolean truthy(Object v) {
        return switch (v) {
            case null -> false;
            case Boolean b -> b;
            case String s -> !s.isEmpty();
            case Json.Number n -> n.value() != 0.0;
            case List<?> l -> !l.isEmpty();
            case Map<?, ?> m -> !m.isEmpty();
            default -> true;
        };
    }

    /** Python {@code int(v)}. */
    static BigInteger pyInt(Object v, String name) {
        try {
            return switch (v) {
                case Boolean b -> b ? BigInteger.ONE : BigInteger.ZERO;
                case Json.Number n -> new BigDecimal(n.text()).toBigInteger();
                case Long l -> BigInteger.valueOf(l);
                case String s -> new BigInteger(s.strip());
                case null, default -> throw new QfError("E_INPUT", name + " is not an integer", name);
            };
        } catch (NumberFormatException e) {
            throw new QfError("E_INPUT", name + " is not an integer", name);
        }
    }

    /** Raises E_UNSUPPORTED_OPERATION for any mode other than "simulated" (HR-42). */
    static void simulatedOnly(Map<?, ?> order) {
        Object mode = order.containsKey("mode") ? order.get("mode") : "simulated";
        if (!"simulated".equals(mode)) {
            throw new QfError("E_UNSUPPORTED_OPERATION", "paper trading never places live orders", "mode");
        }
    }

    /** {@code paper.pretrade.check}: deterministic; every check runs; reasons in the HR-49 order. */
    static List<String> pretradeCheck(Map<?, ?> order, BigDecimal pRef, BigDecimal position, BigDecimal cash,
            long ordersToday, Map<?, ?> limits) {
        simulatedOnly(order);
        int s = sideSign(order.containsKey("side") ? order.get("side") : "");
        Object otype = order.get("type");
        if (otype != null && !(otype instanceof String)) {
            throw new QfError("E_SCHEMA", "type must be a string", "type");
        }
        if (!(otype instanceof String t) || !TYPES.contains(t)) {
            throw new QfError("E_INPUT", "unknown type " + otype, "type");
        }
        BigDecimal q = dec(need(order, "quantity", "order/"), "quantity");
        BigDecimal band = dec(need(limits, "price_band", "limits/"), "price_band");
        if (q.signum() <= 0 || pRef.signum() <= 0) {
            throw new QfError("E_DOMAIN", "quantity and reference price must be positive", "quantity");
        }
        BigDecimal limit = null;
        BigDecimal pChk;
        if (t.equals("MARKET")) {
            pChk = mul(pRef, add(BigDecimal.ONE, mul(of(s), band)));
        } else {
            if (!order.containsKey("limit_price")) {
                throw new QfError("E_SCHEMA", "limit_price is missing", "limit_price");
            }
            limit = dec(order.get("limit_price"), "limit_price");
            if (limit.signum() <= 0) {
                throw new QfError("E_DOMAIN", "limit price must be positive", "limit_price");
            }
            pChk = limit;
        }
        BigDecimal after = add(position, mul(of(s), q));
        Object allow = limits.containsKey("allow_short") ? limits.get("allow_short") : Boolean.TRUE;
        boolean[] failed = {
            truthy(limits.get("kill_switch")),
            BigInteger.valueOf(ordersToday).compareTo(pyInt(need(limits, "max_orders_per_day", "limits/"),
                    "max_orders_per_day")) >= 0,
            q.compareTo(dec(need(limits, "max_order_qty", "limits/"), "max_order_qty")) > 0,
            // cross-multiplied, so no division (HR-77)
            limit != null && rng(sub(limit, pRef).abs(MC), "band").compareTo(rng(mul(band, pRef), "band")) > 0,
            rng(mul(q, pChk), "notional").compareTo(dec(need(limits, "max_notional", "limits/"), "max_notional")) > 0,
            after.abs(MC).compareTo(dec(need(limits, "max_abs_position", "limits/"), "max_abs_position")) > 0,
            !truthy(allow) && after.signum() < 0,
            s > 0 && mul(q, pChk).compareTo(cash) > 0,
        };
        List<String> reasons = new ArrayList<>();
        for (int k = 0; k < failed.length; k++) {
            if (failed[k]) {
                reasons.add(REASONS.get(k));
            }
        }
        return reasons;
    }

    // ------------------------------------------------------------------ CLI cases (cli-contract.md, paper.*)

    private static Object req(Map<?, ?> m, String key, String where) {
        Object v = m.get(key);
        if (v == null) {
            throw new QfError("E_SCHEMA", where + key + " is missing", where + key);
        }
        return v;
    }

    /**
     * The E_SCHEMA checks of every fill, before any other check of the case (KR-230, HR-122): each fill an object,
     * side, quantity and price present, and side and each decimal a JSON string (fuzz run 44937631714).
     */
    private static void fillSchema(List<?> fills) {
        for (int k = 0; k < fills.size(); k++) {
            String w = "fills/" + k + "/";
            if (!(fills.get(k) instanceof Map<?, ?> f)) {
                throw new QfError("E_SCHEMA", w + " is not an object", w);
            }
            for (String key : List.of("side", "quantity", "price")) {
                if (!(req(f, key, w) instanceof String)) {
                    throw new QfError("E_SCHEMA", w + key + " must be a string", w + key);
                }
            }
            if (f.containsKey("fee") && !(f.get("fee") instanceof String)) {
                throw new QfError("E_SCHEMA", w + "fee must be a decimal string", w + "fee");
            }
            for (String key : List.of("quantity", "price", "fee")) { // malformed or non-finite before any E_LIMIT
                if (f.containsKey(key)) {
                    parse((String) f.get(key), w + key);
                }
            }
        }
    }

    /**
     * Fills in the KR-230 order over the whole list: schema, decimals (malformed, then E_LIMIT), unknown side
     * (structural E_INPUT), then a non-positive quantity or price (E_DOMAIN).
     */
    private static List<DayFill> fillList(List<?> fills) {
        fillSchema(fills);
        List<BigDecimal[]> parsed = new ArrayList<>();
        for (int k = 0; k < fills.size(); k++) {
            String w = "fills/" + k + "/";
            Map<?, ?> f = (Map<?, ?>) fills.get(k);
            parsed.add(new BigDecimal[] {dstr(f.get("quantity"), w + "quantity"), dstr(f.get("price"), w + "price"),
                dstr(f.containsKey("fee") ? f.get("fee") : "0", w + "fee")});
        }
        for (Object f : fills) {
            sideSign(((Map<?, ?>) f).get("side"));
        }
        List<DayFill> out = new ArrayList<>();
        for (int k = 0; k < fills.size(); k++) {
            BigDecimal[] v = parsed.get(k);
            if (v[0].signum() <= 0 || v[1].signum() <= 0) {
                throw new QfError("E_DOMAIN", "quantity and price must be positive", "fills/" + k + "/quantity");
            }
            out.add(new DayFill(SYM, ((Map<?, ?>) fills.get(k)).get("side"), v[0], v[1], v[2]));
        }
        return out;
    }

    /** {@code paper.book.apply_fill}: fills in order on one symbol (HR-50); {@code cash_delta} without {@code cash}. */
    public static Map<String, Object> bookCase(List<?> fills, Object cash, Object position, Object avgCost) {
        fillSchema(fills);
        Object[][] scalars = {{cash, "cash"}, {position, "position"}, {avgCost, "avg_cost"}};
        for (Object[] sc : scalars) {
            if (sc[0] != null) {
                schemaDec(sc[0], (String) sc[1]);
            }
        }
        BigDecimal start = cash == null ? BigDecimal.ZERO : dstr(cash, "cash");
        Book book = new Book(start);
        Position pos = book.pos(SYM);
        pos.n = dstr(position, "position");
        pos.c = dstr(avgCost, "avg_cost");
        for (DayFill f : fillList(fills)) {
            book.applyFill(SYM, f.side(), f.quantity(), f.price(), f.fee());
        }
        Map<String, Object> out = new TreeMap<>();
        out.put("position", fmt(pos.n));
        out.put("avg_cost", fmt(pos.c));
        out.put("realised", fmt(book.realised));
        out.put("fees", fmt(book.fees));
        out.put("label", LABEL);
        out.put(cash == null ? "cash_delta" : "cash", fmt(book.cash));
        return out;
    }

    /** {@code paper.book.end_of_day} with {@code paper.pnl.explain} for one symbol (HR-51 to HR-53). */
    public static Map<String, Object> dayCase(Object cashOpen, List<?> fills, Object positionOpen, Object avgCostOpen,
            Object prevClose, Object close, long days, Object cashRate, Object debitRate, Object borrowRate) {
        fillSchema(fills);
        Object[][] scalars = {{cashOpen, "cash_open"}, {positionOpen, "position_open"},
            {avgCostOpen, "avg_cost_open"}, {prevClose, "prev_close"}, {close, "close"}, {cashRate, "cash_rate"},
            {debitRate, "debit_rate"}, {borrowRate, "borrow_rate"}};
        for (Object[] sc : scalars) { // every E_SCHEMA before any E_LIMIT or E_DOMAIN (HR-66, KR-344)
            if (sc[0] != null) {
                schemaDec(sc[0], (String) sc[1]);
            }
        }
        int nSign = parse((String) positionOpen, "position_open").signum();
        if (nSign != 0 && prevClose == null) {
            throw new QfError("E_SCHEMA", "prev_close is missing (open position)", "prev_close");
        }
        if ((nSign != 0 || !fills.isEmpty()) && close == null) {
            throw new QfError("E_SCHEMA", "close is missing (position or fills)", "close");
        }
        BigDecimal cash = dstr(cashOpen, "cash_open");
        BigDecimal n = dstr(positionOpen, "position_open");
        List<DayFill> fl = fillList(fills);
        BigDecimal prev = prevClose == null ? null : dstr(prevClose, "prev_close");
        BigDecimal px = close == null ? null : dstr(close, "close");
        if (prev != null && prev.signum() <= 0) {
            throw new QfError("E_DOMAIN", "prev_close must be positive", "prev_close");
        }
        if (px != null && px.signum() <= 0) {
            throw new QfError("E_DOMAIN", "close must be positive", "close");
        }
        String cr = fmt(dstr(cashRate, "cash_rate"));
        String dr = fmt(dstr(debitRate, "debit_rate"));
        String br = fmt(dstr(borrowRate, "borrow_rate"));
        Book book = new Book(cash);
        Position pos = book.pos(SYM);
        pos.n = n;
        if (avgCostOpen != null) {
            pos.c = dstr(avgCostOpen, "avg_cost_open");
        } else if (prev != null) {
            pos.c = prev;
        }
        Map<String, Object> prevMarks = prev == null ? Map.of() : Map.of(SYM, fmt(prev));
        Map<String, Object> marks = px == null ? Map.of() : Map.of(SYM, fmt(px));
        BigDecimal navOpen = add(cash, n.signum() != 0 && prev != null ? mul(n, prev) : BigDecimal.ZERO);
        Explain e = endOfDay(book, fl, prevMarks, marks, days, cr, dr, br);
        Map<String, Object> out = new TreeMap<>();
        out.put("market", fmt(e.market()));
        out.put("trading", fmt(e.trading()));
        out.put("fees", fmt(e.fees()));
        out.put("financing", fmt(e.fin().financing()));
        out.put("cash_interest", fmt(e.fin().interest()));
        out.put("short_borrow", fmt(e.fin().borrow()));
        out.put("total", fmt(e.total()));
        out.put("position", fmt(pos.n));
        out.put("cash_close", fmt(book.cash));
        out.put("label", LABEL);
        if (px != null) {
            out.put("nav_open", fmt(navOpen));
            out.put("nav_close", fmt(e.nav()));
        }
        return out;
    }

    /** {@code paper.pretrade.check} over the CLI: schema first, then HR-42, then the checks. */
    public static Map<String, Object> pretradeCase(Map<?, ?> order, Object refPrice, Object position, String cash,
            long ordersToday, Map<?, ?> limits) {
        for (String k : List.of("side", "type", "quantity")) {
            req(order, k, "order/");
        }
        for (String k : List.of("side", "type")) { // mistyped is E_SCHEMA; an unlisted string is E_INPUT later
            if (!(order.get(k) instanceof String)) {
                throw new QfError("E_SCHEMA", "order/" + k + " must be a string", "order/" + k);
            }
        }
        Object mo = req(limits, "max_orders_per_day", "limits/");
        if (!(mo instanceof Json.Number n && n.isIntegerForm())) {
            throw new QfError("E_SCHEMA", "limits/max_orders_per_day must be an integer", "limits");
        }
        for (String k : List.of("kill_switch", "allow_short")) {
            if (limits.containsKey(k) && !(limits.get(k) instanceof Boolean)) {
                throw new QfError("E_SCHEMA", "limits/" + k + " must be a boolean", "limits/" + k);
            }
        }
        List<Object[]> scalars = new ArrayList<>();
        scalars.add(new Object[] {order.get("quantity"), "order/quantity"});
        if (order.get("limit_price") != null) {
            scalars.add(new Object[] {order.get("limit_price"), "order/limit_price"});
        }
        for (String k : List.of("max_order_qty", "max_notional", "max_abs_position", "price_band")) {
            scalars.add(new Object[] {req(limits, k, "limits/"), "limits/" + k});
        }
        scalars.add(new Object[] {refPrice, "ref_price"});
        scalars.add(new Object[] {position, "position"});
        scalars.add(new Object[] {cash, "cash"});
        for (Object[] sc : scalars) { // every E_SCHEMA before any E_LIMIT (HR-66, KR-344)
            schemaDec(sc[0], (String) sc[1]);
        }
        dstr(order.get("quantity"), "order/quantity");
        if (order.get("limit_price") != null) {
            dstr(order.get("limit_price"), "order/limit_price");
        }
        for (String k : List.of("max_order_qty", "max_notional", "max_abs_position", "price_band")) {
            dstr(req(limits, k, "limits/"), "limits/" + k);
        }
        List<String> reasons = pretradeCheck(order, dstr(refPrice, "ref_price"), dstr(position, "position"),
                dstr(cash, "cash"), ordersToday, limits);
        Map<String, Object> out = new TreeMap<>();
        out.put("accepted", reasons.isEmpty());
        out.put("reasons", reasons);
        out.put("label", LABEL);
        return out;
    }

    // ------------------------------------------------------------------ simulated fills and session (HR-47, HR-48)

    record Fill(BigDecimal quantity, BigDecimal price, BigDecimal fee, String venue, String childId) {}

    record Child(List<Fill> fills, BigDecimal resting) {}

    static BigDecimal mid(Map<?, ?> snap) {
        if (!(snap.get("bids") instanceof List<?> b) || b.isEmpty() || !(snap.get("asks") instanceof List<?> a)
                || a.isEmpty()) {
            throw new QfError("E_INPUT", "snapshot has an empty side; no mid", "snapshot");
        }
        return div(add(dec(top(b), "bid"), dec(top(a), "ask")), of(2));
    }

    private static Object top(List<?> side) {
        if (!(side.getFirst() instanceof List<?> lv) || lv.isEmpty()) {
            throw new QfError("E_SCHEMA", "snapshot level is not a [price, qty] pair", "snapshot");
        }
        return lv.getFirst();
    }

    private static List<Object> seed(Map<?, ?> snap) {
        List<Object> ev = new ArrayList<>();
        for (String name : List.of("asks", "bids")) {
            String side = name.equals("asks") ? "SELL" : "BUY";
            if (!(snap.get(name) instanceof List<?> levels)) {
                throw new QfError("E_SCHEMA", "snapshot/" + name + " is not an array", "snapshot");
            }
            for (int i = 0; i < levels.size(); i++) {
                if (!(levels.get(i) instanceof List<?> lv) || lv.size() != 2) {
                    throw new QfError("E_SCHEMA", "snapshot/" + name + "/" + i + ": not a [price, qty] pair", "snapshot");
                }
                Map<String, Object> e = new LinkedHashMap<>();
                e.put("op", "NEW");
                e.put("id", "BOOK-" + name + "-" + i);
                e.put("trader", "BOOK");
                e.put("side", side);
                e.put("type", "LIMIT");
                e.put("price", lv.get(0));
                e.put("qty", lv.get(1));
                ev.add(e);
            }
        }
        return ev;
    }

    private static String str(Object v, String name) {
        if (!(v instanceof String s)) {
            throw new QfError("E_SCHEMA", name + " must be a string", name);
        }
        return s;
    }

    /** Replays one child into the lit engine seeded with the snapshot. */
    static Child litChild(Map<?, ?> cfg, Map<?, ?> snap, String cid, Object side, String otype, BigDecimal qty,
            BigDecimal limit) {
        Map<String, Object> ev = new LinkedHashMap<>();
        ev.put("op", "NEW");
        ev.put("id", cid);
        ev.put("trader", TRADER);
        ev.put("side", side);
        ev.put("type", otype);
        ev.put("qty", fmt(qty));
        if (!otype.equals("MARKET")) {
            ev.put("price", fmt(limit));
        }
        if (!(cfg.get("fee_schedule") instanceof Map<?, ?> fees)) {
            throw new QfError("E_SCHEMA", "lit/fee_schedule must be an object", "lit/fee_schedule");
        }
        List<Object> events = seed(snap);
        events.add(ev);
        Map<String, Object> out = LitMatching.run(str(cfg.get("tick_size"), "lit/tick_size"),
                str(cfg.get("lot_size"), "lit/lot_size"), events, fees);
        for (Object r : (List<?>) out.get("rejects")) {
            if (cid.equals(((Map<?, ?>) r).get("id"))) {
                return new Child(List.of(), BigDecimal.ZERO);
            }
        }
        BigDecimal taker = dec(fees.get("taker_fee"), "taker_fee");
        BigDecimal rebate = dec(fees.get("maker_rebate"), "maker_rebate");
        List<Fill> fills = new ArrayList<>();
        for (Object o : (List<?>) out.get("fills")) {
            Map<?, ?> f = (Map<?, ?>) o;
            boolean taking = cid.equals(f.get("taker_id"));
            if (taking || cid.equals(f.get("maker_id"))) {
                BigDecimal q = dec(f.get("qty"), "qty");
                BigDecimal p = dec(f.get("price"), "price");
                BigDecimal rate = taking ? taker : rebate.negate(MC);
                fills.add(new Fill(q, p, mul(mul(rate, q), p), "LIT", cid));
            }
        }
        Map<?, ?> cons = (Map<?, ?>) ((Map<?, ?>) out.get("conservation")).get(cid);
        return new Child(fills, dec(cons.get("resting"), "resting"));
    }

    /** Replays one child into the dark pool at the snapshot mid against the caller's contra events. */
    static Child darkChild(Map<?, ?> cfg, Map<?, ?> snap, List<?> contra, String cid, Object side, BigDecimal qty,
            BigDecimal limit) {
        Map<String, Object> book = new LinkedHashMap<>();
        book.put("op", "BOOK");
        book.put("bid", top((List<?>) snap.get("bids")));
        book.put("ask", top((List<?>) snap.get("asks")));
        Map<String, Object> ev = new LinkedHashMap<>();
        ev.put("op", "NEW");
        ev.put("id", cid);
        ev.put("side", side);
        ev.put("qty", fmt(qty));
        ev.put("kind", "FIRM");
        if (limit != null) {
            ev.put("limit", fmt(limit));
        }
        List<Object> events = new ArrayList<>();
        events.add(book);
        for (Object c : contra) {
            if (!(c instanceof Map<?, ?> m)) {
                throw new QfError("E_SCHEMA", "contra events must be objects", "contra");
            }
            events.add(new LinkedHashMap<>(m));
        }
        events.add(ev);
        Map<String, Object> out = DarkPool.run(cfg, events);
        List<Fill> fills = new ArrayList<>();
        for (Object o : (List<?>) out.get("fills")) {
            Map<?, ?> f = (Map<?, ?>) o;
            if (cid.equals(f.get("buy_id")) || cid.equals(f.get("sell_id"))) {
                fills.add(new Fill(dec(f.get("qty"), "qty"), dec(f.get("price"), "price"), BigDecimal.ZERO, "DARK",
                        cid));
            }
        }
        BigDecimal rest = BigDecimal.ZERO;
        for (Object o : (List<?>) out.get("resting")) {
            Map<?, ?> r = (Map<?, ?>) o;
            if (cid.equals(r.get("id"))) {
                rest = dec(r.get("open_qty"), "q");
                break;
            }
        }
        return new Child(fills, rest);
    }

    private static final class Open {
        final Map<?, ?> order;
        final BigDecimal decision;
        final BigDecimal arrival;
        List<Fill> fills = List.of();
        BigDecimal resting = BigDecimal.ZERO;

        Open(Map<?, ?> order, BigDecimal decision, BigDecimal arrival) {
            this.order = order;
            this.decision = decision;
            this.arrival = arrival;
        }
    }

    /** One paper account: pre-trade gate, simulated fills, ledger, TCA per order, daily close. */
    public static final class Session {
        final Ledger ledger = new Ledger();
        final Book book;
        final Map<?, ?> limits;
        final Map<?, ?> litCfg;
        final Map<?, ?> darkCfg;
        List<Open> today = new ArrayList<>();
        List<DayFill> dayFills = new ArrayList<>();
        long ordersToday;

        public Session(Object cash, Map<?, ?> limits, Map<?, ?> litCfg, Map<?, ?> darkCfg) {
            this.book = new Book(dec(cash, "cash"));
            this.limits = limits;
            this.litCfg = litCfg;
            this.darkCfg = darkCfg;
        }

        BigDecimal position(String symbol) {
            BigDecimal sum = BigDecimal.ZERO;
            BigDecimal n = book.pos(symbol).n;
            for (DayFill f : dayFills) {
                if (f.symbol().equals(symbol)) {
                    sum = add(sum, mul(of(sideSign(f.side())), f.quantity()));
                }
            }
            return add(n, sum);
        }

        BigDecimal cash() {
            BigDecimal sum = BigDecimal.ZERO;
            for (DayFill f : dayFills) {
                sum = add(sum, add(mul(mul(of(sideSign(f.side())), f.quantity()), f.price()), f.fee()));
            }
            return sub(book.cash, sum);
        }

        private Map<?, ?> dark() {
            if (darkCfg == null) {
                throw new QfError("E_SCHEMA", "dark venue configuration is missing", "dark_cfg");
            }
            return darkCfg;
        }

        /** Pre-trade check, then replay into the order's venue; returns the order status. */
        public Map<String, Object> submit(Map<?, ?> order, String ts, Map<?, ?> snap, List<?> contra,
                Map<?, ?> router) {
            Object venue = order.containsKey("venue") ? order.get("venue") : "LIT";
            if (!(venue instanceof String v) || !VENUES.contains(v)) {
                throw new QfError("E_INPUT", "unknown venue " + venue, "venue");
            }
            for (Open o : today) {
                if (Objects.equals(o.order.get("order_id"), order.get("order_id"))) {
                    throw new QfError("E_INPUT", "duplicate order_id", "order_id");
                }
            }
            BigDecimal pRef = mid(snap);
            if (!(order.get("symbol") instanceof String sym)) {
                throw new QfError("E_INPUT", "symbol must be a string", "symbol");
            }
            List<String> reasons = pretradeCheck(order, pRef, position(sym), cash(), ordersToday, limits);
            ordersToday++;
            Map<String, Object> body = new LinkedHashMap<>();
            for (var e : order.entrySet()) {
                if (!"mode".equals(e.getKey())) {
                    body.put((String) e.getKey(), e.getValue());
                }
            }
            Map<String, Object> result = new TreeMap<>();
            if (!reasons.isEmpty()) {
                body.put("reasons", reasons);
                ledger.append("REJECT", ts, body);
                result.put("status", "REJECTED");
                result.put("reasons", reasons);
                return result;
            }
            body.put("decision_price", fmt(pRef));
            ledger.append("ORDER", ts, body);
            Object side = order.get("side");
            if (!(order.get("order_id") instanceof String oid)) {
                throw new QfError("E_INPUT", "order_id must be a string", "order_id");
            }
            String type = (String) order.get("type");
            BigDecimal qty = dec(order.get("quantity"), "quantity");
            BigDecimal limit = type.equals("MARKET") ? null : dec(order.get("limit_price"), "limit_price");
            Open rec = new Open(order, pRef, mid(snap));
            switch (v) {
                case "LIT" -> {
                    Child c = litChild(litCfg, snap, oid, side, type, qty, limit);
                    rec.fills = c.fills();
                    rec.resting = c.resting();
                }
                case "DARK" -> {
                    Child c = darkChild(dark(), snap, contra, oid, side, qty, limit);
                    rec.fills = c.fills();
                    rec.resting = c.resting();
                }
                default -> rec.fills = route(oid, side, snap, contra, router, qty, limit);
            }
            BigDecimal filled = BigDecimal.ZERO;
            for (Fill f : rec.fills) {
                Map<String, Object> fb = new LinkedHashMap<>();
                fb.put("order_id", oid);
                fb.put("child_id", f.childId());
                fb.put("venue", f.venue());
                fb.put("symbol", sym);
                fb.put("side", side);
                fb.put("quantity", fmt(f.quantity()));
                fb.put("price", fmt(f.price()));
                fb.put("fee", fmt(f.fee()));
                ledger.append("FILL", ts, fb);
                // the Python reference re-reads the formatted strings; fmt is exact, so the values are equal
                dayFills.add(new DayFill(sym, side, f.quantity(), f.price(), f.fee()));
                filled = add(filled, f.quantity());
            }
            if (rec.resting.signum() == 0 && filled.compareTo(qty) < 0) {
                ledger.append("CANCEL", ts, cancel(oid, sub(qty, filled)));
            }
            today.add(rec);
            result.put("status", rec.resting.signum() != 0 ? "OPEN" : "DONE");
            result.put("filled", fmt(filled));
            return result;
        }

        private static Map<String, Object> cancel(String oid, BigDecimal q) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("order_id", oid);
            m.put("quantity", fmt(q));
            return m;
        }

        private List<Fill> route(String oid, Object side, Map<?, ?> snap, List<?> contra, Map<?, ?> router,
                BigDecimal qty, BigDecimal limit) {
            if (router == null) {
                throw new QfError("E_SCHEMA", "SOR order needs the router input", "router");
            }
            Map<Object, Object> inp = new LinkedHashMap<>(router);
            inp.put("S", fmt(qty));
            Map<String, Object> alloc = Sor.allocate(inp);
            Object best = top((List<?>) snap.get("BUY".equals(side) ? "bids" : "asks"));
            List<Object[]> children = new ArrayList<>();
            children.add(new Object[] {"M", "MARKET", dec(alloc.get("M"), "M")});
            List<?> venues = (List<?>) router.get("venues");
            List<?> ls = (List<?>) alloc.get("L");
            if (venues.size() != ls.size()) {
                throw new IllegalStateException("router venues and allocation differ in length");
            }
            for (int k = 0; k < venues.size(); k++) {
                children.add(new Object[] {"L" + k, ((Map<?, ?>) venues.get(k)).get("kind"), dec(ls.get(k), "L")});
            }
            List<Fill> fills = new ArrayList<>();
            for (Object[] ch : children) {
                BigDecimal q = (BigDecimal) ch[2];
                if (q.signum() == 0) {
                    continue;
                }
                String cid = oid + "." + ch[0];
                Child got;
                if ("MARKET".equals(ch[1])) {
                    got = litChild(litCfg, snap, cid, side, "MARKET", q, null);
                } else if ("LIT".equals(ch[1])) {
                    got = litChild(litCfg, snap, cid, side, "LIMIT", q, dec(best, "best"));
                } else {
                    got = darkChild(dark(), snap, contra, cid, side, q, limit);
                }
                for (Fill g : got.fills()) { // the parent never overfills
                    BigDecimal sum = BigDecimal.ZERO;
                    for (Fill x : fills) {
                        sum = add(sum, x.quantity());
                    }
                    BigDecimal room = sub(qty, sum);
                    if (room.signum() <= 0) {
                        break;
                    }
                    if (g.quantity().compareTo(room) > 0) {
                        g = new Fill(room, g.price(), div(mul(g.fee(), room), g.quantity()), g.venue(), g.childId());
                    }
                    fills.add(g);
                }
            }
            return fills;
        }

        /** Cancels resting remainders (HR-48), writes one TCA per final order, then the EOD record. */
        public Map<String, Object> closeDay(String ts, Map<?, ?> prevMarks, Map<?, ?> marks, long days,
                Object cashRate, Object debitRate, Object borrowRate) {
            for (Open rec : today) {
                Map<?, ?> o = rec.order;
                String oid = (String) o.get("order_id");
                BigDecimal qty = dec(o.get("quantity"), "quantity");
                BigDecimal filled = BigDecimal.ZERO;
                BigDecimal fees = BigDecimal.ZERO;
                for (Fill f : rec.fills) {
                    filled = add(filled, f.quantity());
                }
                if (rec.resting.signum() != 0) {
                    ledger.append("CANCEL", ts, cancel(oid, sub(qty, filled)));
                }
                for (Fill f : rec.fills) {
                    fees = add(fees, f.fee());
                }
                double[] q = new double[rec.fills.size()];
                double[] p = new double[rec.fills.size()];
                for (int k = 0; k < q.length; k++) {
                    q[k] = toDouble(rec.fills.get(k).quantity());
                    p[k] = toDouble(rec.fills.get(k).price());
                }
                double[] t = tcaShortfall("BUY".equals(o.get("side")), toDouble(rec.decision), toDouble(rec.arrival),
                        toDouble(dec(mark(marks, (String) o.get("symbol")), "close")), toDouble(qty), q, p,
                        toDouble(fees));
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("order_id", oid);
                String[] names = {"delay", "execution", "opportunity", "total", "total_bps"};
                for (int k = 0; k < names.length; k++) {
                    body.put(names[k], fmtDouble(t[k]));
                }
                ledger.append("TCA", ts, body);
            }
            Explain e = endOfDay(book, dayFills, prevMarks, marks, days, cashRate, debitRate, borrowRate);
            Map<String, Object> eod = e.body();
            ledger.append("EOD", ts, eod);
            today = new ArrayList<>();
            dayFills = new ArrayList<>();
            ordersToday = 0;
            return eod;
        }

        public Ledger ledger() {
            return ledger;
        }
    }

    /**
     * {@code exec.tca.shortfall} in binary64 in the order fixed by cli-contract.md (no FMA: Java never contracts):
     * delay, execution, opportunity, total, total_bps.
     */
    static double[] tcaShortfall(boolean buy, double decision, double arrival, double end, double orderQty,
            double[] q, double[] p, double fees) {
        double s = buy ? 1.0 : -1.0;
        if (orderQty <= 0) {
            throw new QfError("E_INPUT", "order_quantity must be positive", "order_quantity");
        }
        double filled = 0.0;
        for (double x : q) {
            if (x <= 0) {
                throw new QfError("E_INPUT", "fill quantities must be positive", "fills");
            }
        }
        for (double x : q) {
            filled = filled + x;
        }
        if (filled > orderQty) {
            throw new QfError("E_INPUT", "fills add up to more than the order", "fills");
        }
        if (decision <= 0 || arrival <= 0 || end <= 0) {
            throw new QfError("E_DOMAIN", "prices must be positive", "price");
        }
        for (double x : p) {
            if (x <= 0) {
                throw new QfError("E_DOMAIN", "prices must be positive", "fills");
            }
        }
        double delay = (s * filled) * (arrival - decision);
        double sum = 0.0;
        for (int k = 0; k < q.length; k++) {
            double term = q[k] * (p[k] - arrival);
            sum = sum + term;
        }
        double execution = s * sum;
        double oppA = s * (orderQty - filled);
        double opportunity = oppA * (end - decision) + 0.0;
        double total = ((delay + execution) + opportunity) + fees;
        double denom = orderQty * decision;
        double bps = (total / denom) * 1e4;
        return new double[] {delay, execution, opportunity, total, bps};
    }

    /** {@code paper.session.run}: replays SUBMIT and CLOSE steps through one Session (A8: deterministic). */
    /**
     * A malformed or non-finite decimal string anywhere in the script is E_SCHEMA before the cash range check
     * (KR-344, HR-66). Only string values are read; every other check of a step stays in step order.
     */
    private static void scriptDecimalSchema(List<?> script) {
        for (int k = 0; k < script.size(); k++) {
            if (!(script.get(k) instanceof Map<?, ?> step)) {
                continue;
            }
            String w = "script/" + k + "/";
            List<Object[]> found = new ArrayList<>();
            if (step.get("order") instanceof Map<?, ?> order) {
                for (String key : List.of("quantity", "limit_price")) {
                    found.add(new Object[] {order.get(key), w + "order/" + key});
                }
            }
            for (String r : List.of("cash_rate", "debit_rate", "borrow_rate")) {
                found.add(new Object[] {step.get(r), w + r});
            }
            for (String name : List.of("prev_marks", "marks")) {
                if (step.get(name) instanceof Map<?, ?> m) {
                    for (Map.Entry<?, ?> ent : m.entrySet()) {
                        found.add(new Object[] {ent.getValue(), w + name + "/" + ent.getKey()});
                    }
                }
            }
            for (Object[] f : found) {
                if (f[0] instanceof String t) {
                    parse(t, (String) f[1]);
                }
            }
        }
    }

    public static Map<String, Object> sessionCase(Object cash, Map<?, ?> limits, Map<?, ?> lit, List<?> script,
            Map<?, ?> dark) {
        schemaDec(cash, "cash");
        for (String k : List.of("tick_size", "lot_size", "fee_schedule")) {
            if (lit.get(k) == null) {
                throw new QfError("E_SCHEMA", "lit/" + k + " is missing", "lit/" + k);
            }
        }
        scriptDecimalSchema(script); // malformed step decimals before the cash range (HR-66, KR-344)
        dstr(cash, "cash");
        Session s = new Session(cash, limits, lit, dark);
        List<Object> results = new ArrayList<>();
        TreeMap<String, Object> symbols = new TreeMap<>(CODE_POINT);
        for (int k = 0; k < script.size(); k++) {
            String w = "script/" + k + "/";
            if (!(script.get(k) instanceof Map<?, ?> step) || !("SUBMIT".equals(step.get("op"))
                    || "CLOSE".equals(step.get("op")))) {
                throw new QfError("E_SCHEMA", w + "op must be SUBMIT or CLOSE", w + "op");
            }
            if (!(step.get("ts") instanceof String ts)) {
                throw new QfError("E_SCHEMA", w + "ts is missing", w + "ts");
            }
            if ("SUBMIT".equals(step.get("op"))) {
                if (!(step.get("order") instanceof Map<?, ?> order) || !(step.get("snapshot") instanceof Map<?, ?> snap)) {
                    throw new QfError("E_SCHEMA", w + "order and snapshot are required", w + "order");
                }
                for (String key : List.of("order_id", "symbol", "side", "type", "quantity")) {
                    if (order.get(key) == null) {
                        throw new QfError("E_SCHEMA", w + "order/" + key + " is missing", w + "order/" + key);
                    }
                }
                // mistyped text fields are E_SCHEMA (fuzz run 44937631714 class); a null venue stays E_INPUT
                for (String key : List.of("order_id", "symbol", "side", "type", "venue")) {
                    Object v = order.get(key);
                    if (v != null && !(v instanceof String)) {
                        throw new QfError("E_SCHEMA", w + "order/" + key + " must be a string", w + "order/" + key);
                    }
                }
                for (String key : List.of("quantity", "limit_price")) {
                    if (order.get(key) != null) {
                        dstr(order.get(key), w + "order/" + key);
                    }
                }
                if (order.get("symbol") instanceof String sym) {
                    symbols.put(sym, sym);
                }
                Object c = step.get("contra");
                if (c != null && !(c instanceof List<?>)) {
                    throw new QfError("E_SCHEMA", w + "contra must be an array", w + "contra");
                }
                Object r = step.get("router");
                if (r != null && !(r instanceof Map<?, ?>)) {
                    throw new QfError("E_SCHEMA", w + "router must be an object", w + "router");
                }
                results.add(s.submit(order, ts, snap, c == null ? List.of() : (List<?>) c, (Map<?, ?>) r));
            } else {
                Object days = step.containsKey("days") ? step.get("days") : Long.valueOf(1);
                long d;
                if (days instanceof Long l) {
                    d = l;
                } else if (days instanceof Json.Number n && n.isIntegerForm()) {
                    d = new BigInteger(n.text()).longValueExact();
                } else {
                    throw new QfError("E_SCHEMA", w + "days must be an integer", w + "days");
                }
                Object[] rates = new Object[3];
                String[] rn = {"cash_rate", "debit_rate", "borrow_rate"};
                for (int i = 0; i < 3; i++) {
                    rates[i] = step.containsKey(rn[i]) ? step.get(rn[i]) : "0";
                    dstr(rates[i], w + rn[i]);
                }
                for (String name : List.of("prev_marks", "marks")) {
                    if (step.get(name) instanceof Map<?, ?> m) {
                        for (var e : m.entrySet()) {
                            dstr(e.getValue(), w + name + "/" + e.getKey());
                        }
                    }
                }
                Map<?, ?> pm = step.get("prev_marks") instanceof Map<?, ?> m ? m : Map.of();
                Map<?, ?> mk = step.get("marks") instanceof Map<?, ?> m ? m : Map.of();
                Map<String, Object> eod = s.closeDay(ts, pm, mk, d, rates[0], rates[1], rates[2]);
                Map<String, Object> res = new TreeMap<>();
                res.put("status", "CLOSED");
                res.put("eod", eod);
                results.add(res);
            }
        }
        Map<String, Object> positions = new TreeMap<>(CODE_POINT);
        for (String sym : symbols.keySet()) {
            positions.put(sym, fmt(s.position(sym)));
        }
        Map<String, Object> out = new TreeMap<>();
        out.put("results", results);
        out.put("records", new ArrayList<>(s.ledger.records()));
        out.put("head", s.ledger.head());
        out.put("positions", positions);
        out.put("cash", fmt(s.cash()));
        out.put("label", LABEL);
        out.put("ceiling", CEILING);
        return out;
    }
}
